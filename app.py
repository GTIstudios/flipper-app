from pathlib import Path
from datetime import datetime
from typing import Optional
import zipfile

import streamlit as st
import pandas as pd

from localflipper.config import settings
from localflipper.scraping.craigslist import search_craigslist
from localflipper.scraping.facebook import search_facebook_marketplace
from localflipper.pricing.ebay_api import estimate_ebay_sold_price
from localflipper.pricing.local_pricing_rules import estimate_market_value_and_profit
from localflipper.utils.filters import compute_deal, filter_deals
from localflipper.utils.condition_parser import parse_condition
from localflipper.utils.seller_rating import rate_seller
from localflipper.utils.demand_engine import compute_travel_cost, compute_demand_score
from localflipper.utils.description_cleaner import clean_seller_text
from localflipper import db
from localflipper import google_sheets


# ---------------------------------------------------------
# DEAL SEARCH / ARBITRAGE PIPELINE (Craigslist + Facebook)
# ---------------------------------------------------------
def run_search(
    cl_site: str,
    query: str,
    max_cl_price: float | None,
    max_cl_results: int,
    postal: str,
    distance: int,
    min_profit: float,
    min_margin_pct: float,
    include_facebook: bool,
    mpg: float,
    gas_price: float,
) -> pd.DataFrame:
    """
    Unified arbitrage search:
    - Craigslist (always)
    - Facebook Marketplace (optional, via include_facebook)

    Returns a single DataFrame sorted by estimated profit.
    """

    # 1. Craigslist
    cl_listings = search_craigslist(
        site=cl_site,
        query=query,
        max_price=max_cl_price,
        postal=postal,
        distance=distance,
        max_results=max_cl_results,
    )

    # 2. Facebook
    if include_facebook:
        fb_listings = search_facebook_marketplace(
            query=query,
            location=postal,
            radius_miles=distance,
            max_results=max_cl_results,
        )
    else:
        fb_listings = []

    all_deal_candidates = []

    def process_listings(listings, source_label: str):
        for listing in listings:
            # Make sure listing has a source label
            listing.source = source_label
            ebay_info = estimate_ebay_sold_price(listing.title)
            deal = compute_deal(listing, ebay_info)
            if deal:
                all_deal_candidates.append(deal)

    process_listings(cl_listings, "craigslist")
    if include_facebook:
        process_listings(fb_listings, "facebook")

    # Existing profit filters (may be 0 / raw mode if no real eBay API yet)
    filtered = filter_deals(
        all_deal_candidates,
        min_profit=min_profit,
        min_margin_pct=min_margin_pct,
    )

    if not filtered:
        return pd.DataFrame()

    # Travel cost is roughly the same per run (radius-based)
    travel_cost = compute_travel_cost(distance, mpg, gas_price)

    rows = []
    for d in filtered:
        title = d.listing.title or ""
        local_price = float(d.listing.price or 0.0)

        # Condition / seller rating (title-based for now)
        condition_label, condition_score, _matches = parse_condition(title)
        seller_rating, _reds, _greens = rate_seller(title)

        # Rule-based market value (independent of eBay)
        est_value, rule_profit = estimate_market_value_and_profit(
            local_price=local_price,
            condition_score=condition_score,
        )

        # Demand score uses rule profit + title/query
        demand_score = compute_demand_score(
            title=title,
            category_hint=query,
            condition_score=condition_score,
            rule_profit=rule_profit,
        )

        # Effective profit (rule-based) after travel
        effective_profit = round(rule_profit - travel_cost, 2)

        est_profit = round(float(d.estimated_profit or 0.0), 2)
        profit_pct = round(float(d.profit_margin_pct or 0.0), 1)

        rows.append(
            {
                "Source": d.listing.source,
                "Title": title,
                "Location": d.listing.location,
                "Local Price": local_price,
                # Existing eBay-based fields (may be 0 in raw mode)
                "eBay Avg Sold": d.ebay.average_sold_price,
                "Est Profit (eBay)": est_profit,
                "Profit % (eBay)": profit_pct,
                "Samples": d.ebay.sample_size,
                # New rule-based pricing fields
                "Condition Guess": condition_label,
                "Condition Score": condition_score,
                "Seller Rating": seller_rating,
                "Rule Market Value": est_value,
                "Rule Profit Est": rule_profit,
                "Travel Cost Est": travel_cost,
                "Effective Profit (Rule)": effective_profit,
                "Demand Score": demand_score,
                # Links
                "Listing Link": d.listing.url,
                "eBay Search": f"https://www.ebay.com/sch/i.html?_nkw={title.replace(' ', '+')}",
            }
        )

    df = pd.DataFrame(rows)
    # Primary sort by Demand Score, secondary by Effective Profit
    df = df.sort_values(
        by=["Demand Score", "Effective Profit (Rule)"],
        ascending=[False, False],
    )
    return df


def export_results_to_csv(df: pd.DataFrame, mode: str) -> Path:
    """Export DataFrame to CSV under exports/ and return path."""
    exports_dir = Path("exports")
    exports_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"localflipper_{mode}_{timestamp}.csv"
    path = exports_dir / filename

    df.to_csv(path, index=False)
    return path


# ---------------------------------------------------------
# LISTING COMPOSER HELPERS
# ---------------------------------------------------------
def generate_ai_description(
    style: str,
    title: str,
    price: float,
    condition: str,
    category: str,
    location: str,
) -> str:
    title_clean = title.strip() or "This item"
    price_str = f"${price:,.2f}" if price > 0 else "a fair price"
    condition_text = condition or "Good"
    category_text = category.strip() or "General"

    location_line = ""
    if location.strip():
        location_line = f"Located in {location.strip()}. "

    if "ps5" in title_clean.lower() or "playstation" in title_clean.lower():
        base_features = (
            "Next-gen PlayStation 5 console ideal for 4K gaming, streaming, and Blu-ray. "
            "Fast SSD load times, smooth performance, and support for the latest titles."
        )
    elif "xbox" in title_clean.lower():
        base_features = (
            "Powerful Xbox console great for high-frame-rate gaming, Game Pass, and 4K entertainment."
        )
    elif any(k in title_clean.lower() for k in ["laptop", "notebook", "macbook"]):
        base_features = (
            "Reliable laptop ideal for work, school, and streaming. Ready for productivity or light gaming."
        )
    else:
        base_features = (
            f"Solid {category_text.lower()} item in {condition_text.lower()} condition. "
            "Good for everyday use and a sensible pickup at the right price."
        )

    style = style.lower()
    if style == "viral hook":
        lines = [
            f"STOP SCROLLING — {title_clean} just hit the market and it's in {condition_text.lower()} condition.",
            "",
            f"Price: {price_str}. {location_line}First come, first served.",
            "",
            base_features,
            "",
            "Why you’ll like it:",
            "- Clean and ready to use",
            "- Priced to move",
            "- Great for daily use, gifts, or upgrades",
            "",
            "If this post is up, it’s still available. Message me today to claim it.",
        ]
    elif style == "professional":
        lines = [
            f"{title_clean} — {condition_text} Condition",
            "",
            f"Offered at {price_str}. {location_line}",
            base_features,
            "",
            "Details:",
            f"- Condition: {condition_text}",
            f"- Category: {category_text}",
            "- Tested and working as expected (unless otherwise stated).",
            "",
            "Local buyers preferred. Serious inquiries only, please.",
        ]
    elif style == "quick sell":
        lines = [
            f"{title_clean} for sale — {condition_text} condition.",
            "",
            f"Price: {price_str}. {location_line}",
            "Works as it should. Priced to sell quickly.",
            "",
            "Pickup only. Cash or simple payment on meetup. First reasonable offer takes it.",
        ]
    else:
        lines = [
            f"I’m selling my {title_clean.lower()} that’s in {condition_text.lower()} condition.",
            "",
            f"I originally picked this up for {category_text.lower()} use, and it has served well. "
            "Now I’m downsizing and letting it go to someone who’ll actually use it.",
            "",
            f"Price is {price_str}. {location_line}",
            base_features,
            "",
            "If you’re local and looking for a good deal, this is a solid pickup. "
            "Reach out with any questions or to set up a time to check it out.",
        ]

    return "\n".join(lines)


def format_listing_for_platform(
    platform: str,
    title: str,
    price: float,
    condition: str,
    category: str,
    location: str,
    description: str,
    local_only: bool,
) -> str:
    price_str = f"${price:,.2f}" if price > 0 else "Best offer"
    base_lines: list[str] = [
        f"Title: {title}",
        f"Price: {price_str}",
        f"Condition: {condition}",
    ]

    if category.strip():
        base_lines.append(f"Category: {category.strip()}")

    if location.strip():
        base_lines.append(f"Location: {location.strip()}")

    base_lines.append("")

    if description.strip():
        base_lines.append("Description:")
        base_lines.append(description.strip())
        base_lines.append("")

    notes: list[str] = []

    if platform.lower() == "facebook":
        notes.append("Platform: Facebook Marketplace")
        if local_only:
            notes.append("Pickup: Local pickup only. No shipping.")
        else:
            notes.append("Pickup/Shipping: Local pickup preferred. Shipping may be available.")
        notes.append("Payments: Cash, Venmo, or as agreed on pickup.")
    elif platform.lower() == "craigslist":
        notes.append("Platform: Craigslist")
        if local_only:
            notes.append("Terms: Local cash sale only. No shipping.")
        else:
            notes.append("Terms: Local sale preferred. Shipping possible if buyer pays in advance.")
    elif platform.lower() == "offerup":
        notes.append("Platform: OfferUp")
        if local_only:
            notes.append("Pickup: Local meetup in a public place. No shipping.")
        else:
            notes.append("Pickup/Shipping: Local meetup or app-enabled shipping.")
    else:
        notes.append(f"Platform: {platform}")

    combined = base_lines + [""] + notes
    return "\n".join(combined)


def save_listing_to_files(
    title: str,
    fb_text: str,
    cl_text: str,
    offerup_text: str,
    uploaded_photos: Optional[list] = None,
) -> tuple[Path, Optional[Path]]:
    listings_dir = Path("listings")
    listings_dir.mkdir(exist_ok=True)

    safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip()
    if not safe_title:
        safe_title = "listing"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"{safe_title}_{timestamp}".replace(" ", "_")

    folder = listings_dir / base_name
    folder.mkdir(exist_ok=True)

    fb_path = folder / "facebook.txt"
    cl_path = folder / "craigslist.txt"
    offerup_path = folder / "offerup.txt"

    fb_path.write_text(fb_text, encoding="utf-8")
    cl_path.write_text(cl_text, encoding="utf-8")
    offerup_path.write_text(offerup_text, encoding="utf-8")

    photos_dir = folder / "photos"
    photo_paths: list[Path] = []

    if uploaded_photos:
        photos_dir.mkdir(exist_ok=True)
        for idx, file in enumerate(uploaded_photos, start=1):
            ext = Path(file.name).suffix.lower() or ".jpg"
            filename = f"img_{idx:02d}{ext}"
            out_path = photos_dir / filename
            out_path.write_bytes(file.read())
            photo_paths.append(out_path)

    zip_path = listings_dir / f"{base_name}.zip"
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(fb_path, arcname=fb_path.name)
            zf.write(cl_path, arcname=cl_path.name)
            zf.write(offerup_path, arcname=offerup_path.name)
            for p in photo_paths:
                zf.write(p, arcname=f"photos/{p.name}")
    except Exception:
        zip_path = None

    return folder, zip_path


# ---------------------------------------------------------
# MAIN STREAMLIT APP
# ---------------------------------------------------------
def main():
    st.set_page_config(page_title="LocalFlipper Arbitrage App", layout="wide")
    st.title("LocalFlipper — Local Deals & Listing Composer")

    if "last_results" not in st.session_state:
        st.session_state["last_results"] = None
    if "last_mode" not in st.session_state:
        st.session_state["last_mode"] = None
    if "listing_description" not in st.session_state:
        st.session_state["listing_description"] = ""
    if "ai_description_preview" not in st.session_state:
        st.session_state["ai_description_preview"] = ""

    saved_searches = db.get_saved_searches()

    # Sidebar
    with st.sidebar:
        st.header("Search Settings")

        cl_site = st.text_input(
            "Craigslist Region (subdomain)",
            value=settings.DEFAULT_CRAIGSLIST_SITE,
        )

        postal = st.text_input(
            "Postal Code",
            value="96001",
            help="Starting ZIP for radius search.",
        )

        distance = st.slider(
            "Search Radius (miles)",
            min_value=0,
            max_value=200,
            value=50,
            step=10,
        )

        query = st.text_input(
            "Search Keywords (single search)",
            value="ps5",
        )

        max_cl_price = st.number_input(
            "Max Local Price (Craigslist/FB) (optional)",
            min_value=0.0,
            value=0.0,
        )
        if max_cl_price <= 0:
            max_cl_price = None

        max_cl_results = st.slider(
            "Max Local Results Per Source",
            min_value=10,
            max_value=200,
            value=50,
        )

        st.header("Deal Filters")

        min_profit = st.number_input(
            "Minimum Estimated Profit (eBay) ($)",
            min_value=0.0,
            value=0.0,
            help="Set to 0 while eBay API is not active or in raw mode.",
        )

        min_margin_pct = st.number_input(
            "Minimum Profit Margin (eBay) (%)",
            min_value=0.0,
            value=0.0,
        )

        include_facebook = st.checkbox(
            "Include Facebook Marketplace results",
            value=False,
            help="Once facebook.py scraper is wired, this will also pull Marketplace deals.",
        )

        st.header("Travel Cost Settings")
        mpg = st.number_input(
            "Your Car MPG",
            min_value=5.0,
            max_value=80.0,
            value=22.0,
        )
        gas_price = st.number_input(
            "Gas Price ($/gallon)",
            min_value=1.0,
            max_value=10.0,
            value=4.50,
        )

        st.markdown("---")
        st.subheader("Saved Searches")

        if saved_searches:
            st.write("Current saved terms:")
            st.write(", ".join(saved_searches))
        else:
            st.write("No saved searches yet.")

        new_saved_term = st.text_input(
            "Add new saved search term",
            value="",
            key="new_saved_search_term",
        )

        add_saved_btn = st.button("Add to Saved Searches", key="btn_add_saved")
        run_single_btn = st.button("Run Single Search", key="btn_run_single")
        run_saved_btn = st.button("Run All Saved Searches", key="btn_run_saved")

    deals_tab, listing_tab = st.tabs(["Find Deals", "Create Listing"])

    # -----------------------------------------------------
    # TAB 1: FIND DEALS
    # -----------------------------------------------------
    with deals_tab:
        if add_saved_btn:
            if new_saved_term.strip():
                db.add_saved_search(new_saved_term)
                st.success(f"Added saved search: {new_saved_term.strip()}")
            else:
                st.warning("Cannot add an empty search term.")

        results_df = None
        mode: Optional[str] = None

        if run_single_btn:
            if not query.strip():
                st.warning("Please enter a keyword for the single search.")
            else:
                with st.spinner(f"Running single search for '{query.strip()}'..."):
                    results_df = run_search(
                        cl_site=cl_site,
                        query=query.strip(),
                        max_cl_price=max_cl_price,
                        max_cl_results=max_cl_results,
                        postal=postal.strip(),
                        distance=distance,
                        min_profit=min_profit,
                        min_margin_pct=min_margin_pct,
                        include_facebook=include_facebook,
                        mpg=mpg,
                        gas_price=gas_price,
                    )
                mode = "single"
                st.session_state["last_results"] = results_df
                st.session_state["last_mode"] = mode

        if run_saved_btn:
            if not saved_searches:
                st.warning("No saved searches to run. Add some terms first.")
            else:
                all_frames = []
                with st.spinner("Running all saved searches..."):
                    for term in saved_searches:
                        df_term = run_search(
                            cl_site=cl_site,
                            query=term,
                            max_cl_price=max_cl_price,
                            max_cl_results=max_cl_results,
                            postal=postal.strip(),
                            distance=distance,
                            min_profit=min_profit,
                            min_margin_pct=min_margin_pct,
                            include_facebook=include_facebook,
                            mpg=mpg,
                            gas_price=gas_price,
                        )
                        if not df_term.empty:
                            df_term.insert(0, "Search Term", term)
                            all_frames.append(df_term)

                if all_frames:
                    combined = pd.concat(all_frames, ignore_index=True)
                    combined = combined.sort_values(
                        by=["Demand Score", "Effective Profit (Rule)"],
                        ascending=[False, False],
                    )
                    results_df = combined
                    mode = "saved"
                    st.session_state["last_results"] = results_df
                    st.session_state["last_mode"] = mode
                else:
                    st.info("No deals found for any saved searches with current filters.")

        if results_df is None:
            results_df = st.session_state.get("last_results")
            mode = st.session_state.get("last_mode")

        if results_df is not None and not results_df.empty:
            if mode == "single":
                st.subheader(f"Results for '{query.strip()}'")
            elif mode == "saved":
                st.subheader("Results for all saved searches")
            else:
                st.subheader("Results")

            st.dataframe(results_df, use_container_width=True)

            st.markdown("---")
            st.subheader("Export & Sync")

            export_btn = st.button("Export Results to CSV", key="btn_export_csv")
            sheet_name = st.text_input(
                "Google Sheets Tab Name",
                value="LocalFlipperDeals",
                help="Name of the worksheet/tab inside the spreadsheet.",
                key="sheet_name_input",
            )
            sync_btn = st.button("Sync Results to Google Sheets", key="btn_sync_sheets")

            if export_btn:
                try:
                    path = export_results_to_csv(results_df, mode or "unknown")
                    st.success(f"Exported to CSV: {path}")
                except Exception as e:
                    st.error(f"Failed to export CSV: {e}")

            if sync_btn:
                try:
                    google_sheets.append_dataframe_to_sheet(results_df, sheet_name)
                    st.success(
                        f"Synced {len(results_df)} rows to Google Sheets tab '{sheet_name}'."
                    )
                except Exception as e:
                    st.error(f"Failed to sync to Google Sheets: {e}")
                    st.info(
                        "Make sure GOOGLE_SHEETS_SPREADSHEET_ID is set in .env and "
                        "credentials.json exists in localflipper/credentials."
                    )

        elif results_df is not None and results_df.empty:
            st.info("No deals found. Try loosening your filters or changing your search terms.")

    # -----------------------------------------------------
    # TAB 2: CREATE LISTING (AI description + photos + clean seller text)
    # -----------------------------------------------------
    with listing_tab:
        st.subheader("Listing Composer (Facebook / Craigslist / OfferUp)")

        col1, col2 = st.columns(2)

        with col1:
            listing_title = st.text_input("Listing Title", value="PlayStation 5 with 2 Controllers")
            listing_price = st.number_input("Price", min_value=0.0, value=450.0, step=5.0)
            condition = st.selectbox(
                "Condition",
                ["New", "Like New", "Good", "Fair", "For Parts"],
                index=1,
            )
            category = st.text_input("Category (optional)", value="Video Games & Consoles")
            location = st.text_input("Your City / Area", value="Redding, CA")
            local_only = st.checkbox("Local pickup only (no shipping)", value=True)

        with col2:
            st.markdown("### AI Description Generator")
            style_choice = st.selectbox(
                "AI Description Style",
                ["Viral Hook", "Professional", "Quick Sell", "Story"],
                index=0,
                key="ai_style_choice",
            )

            gen_ai_btn = st.button("Generate Description with AI", key="btn_ai_desc")

            if gen_ai_btn:
                if not listing_title.strip():
                    st.warning("Please enter a listing title before generating a description.")
                else:
                    ai_desc = generate_ai_description(
                        style=style_choice,
                        title=listing_title,
                        price=listing_price,
                        condition=condition,
                        category=category,
                        location=location,
                    )
                    st.session_state["listing_description"] = ai_desc
                    st.session_state["ai_description_preview"] = ai_desc

            st.markdown("### Clean Seller Description (Optional)")
            raw_seller_desc = st.text_area(
                "Paste seller's raw description here (from Craigslist/FB):",
                value="",
                height=100,
            )
            clean_btn = st.button("Clean Seller Description", key="btn_clean_seller_desc")
            if clean_btn:
                cleaned = clean_seller_text(raw_seller_desc)
                st.text_area(
                    "Cleaned Description",
                    value=cleaned,
                    height=200,
                    key="cleaned_seller_desc",
                )

        description = st.text_area(
            "Description / Details",
            value=st.session_state.get("listing_description", ""),
            height=160,
        )

        if st.session_state.get("ai_description_preview"):
            st.markdown("### AI-Generated Preview")
            st.text_area(
                "AI Preview (read-only)",
                value=st.session_state["ai_description_preview"],
                height=200,
                disabled=True,
            )

        st.markdown("### Upload Photos")
        uploaded_photos = st.file_uploader(
            "Upload Listing Photos",
            type=["jpg", "jpeg", "png"],
            accept_multiple_files=True,
            key="listing_photos",
        )

        if uploaded_photos:
            st.write(f"{len(uploaded_photos)} photo(s) selected:")
            preview_cols = st.columns(min(3, len(uploaded_photos)))
            for idx, file in enumerate(uploaded_photos):
                col = preview_cols[idx % len(preview_cols)]
                with col:
                    st.image(file, caption=file.name, use_container_width=True)

        generate_btn = st.button("Generate Platform Text", key="btn_generate_listing")

        if generate_btn:
            if not listing_title.strip():
                st.warning("Please enter a listing title.")
            else:
                fb_text = format_listing_for_platform(
                    platform="facebook",
                    title=listing_title,
                    price=listing_price,
                    condition=condition,
                    category=category,
                    location=location,
                    description=description,
                    local_only=local_only,
                )

                cl_text = format_listing_for_platform(
                    platform="craigslist",
                    title=listing_title,
                    price=listing_price,
                    condition=condition,
                    category=category,
                    location=location,
                    description=description,
                    local_only=local_only,
                )

                offerup_text = format_listing_for_platform(
                    platform="offerup",
                    title=listing_title,
                    price=listing_price,
                    condition=condition,
                    category=category,
                    location=location,
                    description=description,
                    local_only=local_only,
                )

                st.markdown("### Facebook Marketplace Version")
                st.text_area(
                    "Facebook Text",
                    value=fb_text,
                    height=200,
                    key="fb_text_area",
                )
                st.download_button(
                    "Download Facebook Text",
                    data=fb_text,
                    file_name="facebook_listing.txt",
                    mime="text/plain",
                    key="fb_download_btn",
                )

                st.markdown("### Craigslist Version")
                st.text_area(
                    "Craigslist Text",
                    value=cl_text,
                    height=200,
                    key="cl_text_area",
                )
                st.download_button(
                    "Download Craigslist Text",
                    data=cl_text,
                    file_name="craigslist_listing.txt",
                    mime="text/plain",
                    key="cl_download_btn",
                )

                st.markdown("### OfferUp Version")
                st.text_area(
                    "OfferUp Text",
                    value=offerup_text,
                    height=200,
                    key="offerup_text_area",
                )
                st.download_button(
                    "Download OfferUp Text",
                    data=offerup_text,
                    file_name="offerup_listing.txt",
                    mime="text/plain",
                    key="offerup_download_btn",
                )

                st.markdown("---")
                save_btn = st.button(
                    "Save Listing Files to /listings and Create ZIP",
                    key="btn_save_listing_files",
                )

                if save_btn:
                    try:
                        folder, zip_path = save_listing_to_files(
                            title=listing_title,
                            fb_text=fb_text,
                            cl_text=cl_text,
                            offerup_text=offerup_text,
                            uploaded_photos=uploaded_photos,
                        )
                        st.success(f"Saved listing files to: {folder}")

                        if zip_path and zip_path.exists():
                            zip_bytes = zip_path.read_bytes()
                            st.download_button(
                                "Download Full Listing Bundle (ZIP)",
                                data=zip_bytes,
                                file_name=zip_path.name,
                                mime="application/zip",
                                key="zip_download_btn",
                            )
                        else:
                            st.info("ZIP file could not be created, but text files were saved.")
                    except Exception as e:
                        st.error(f"Failed to save listing files: {e}")


if __name__ == "__main__":
    main()
