# 🚀 Flipper App — Local Deals → eBay Profit Analyzer
A Streamlit-powered tool that analyzes local Craigslist and Facebook Marketplace listings and compares them to real eBay market data to identify profitable flips.

This application automates reseller research, allowing you to instantly evaluate whether a local item is worth buying and reselling — without manually checking dozens of listings and sold-history pages.

---

## 📌 Overview
Flipper App streamlines the entire flipping workflow:

- Pulls local listings (Craigslist + Marketplace scraping)
- Normalizes messy product data
- Auto-translates non-English descriptions
- Detects item condition
- Estimates travel cost
- Calculates eBay demand
- Provides target buy prices
- Outputs clean, easy-to-read Smart Listing Cards

This reduces hours of research into seconds.

---

## ✨ Features

### 🔍 Local Search
Search any item by keyword + location radius.

### 🧩 Condition Auto-Parser
Extracts and normalizes condition tags from messy seller descriptions.

### 🌍 Auto-Translate
Automatically translates foreign-language listings into English.

### 📊 Demand Score Engine
Analyzes:
- Local supply
- Pricing trends
- Item rarity
- eBay sold-frequency data

Outputs a **Low / Medium / High demand score**.

### 🚗 Travel-Cost Model
Estimates:
- Round-trip mileage
- Fuel cost
- Impact on net profit

### 💰 Recommended Buy Price
Uses eBay sold-history (API-ready scaffold) to calculate:
- Fair market value
- Recommended buy range
- Expected resale margin

### 📌 Smart Listing Cards
A clean card layout that makes deal evaluation visual and fast.

### 🔐 eBay OAuth2 (Pending Activation)
OAuth2 integration scaffold is built and ready for production keys.

---

## 🛠 Tech Stack
- **Python**
- **Streamlit**
- **BeautifulSoup / Requests**
- **eBay API (OAuth2 Scaffold)**
- **Google Translate API (optional)**
- **Pandas**
- **JSON / REST API handling**

---

## 📦 Installation

```bash
git clone https://github.com/GTIstudios/flipper-app.git
cd flipper-app
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the app:

```bash
streamlit run app.py
```

---

## 🖼 Screenshots (Upload Your Images Here)
Create an **/assets/** folder in the repo and upload:

```
/assets
   home-screen.png
   listing-card-example.png
   demand-score-example.png
   translation-example.png
```

Then add screenshots here:

```markdown
![Home Screen](assets/home-screen.png)
![Listing Card](assets/listing-card-example.png)
![Demand Score](assets/demand-score-example.png)
```

---

## 📂 Project Structure

```
flipper-app/
│
├── app.py
├── requirements.txt
├── utils/
│   ├── condition_parser.py
│   ├── translator.py
│   ├── demand_score.py
│   └── travel_cost.py
├── assets/   ← add screenshots here
└── README.md
```

---

## ⚙️ How It Works
1. User inputs search term + radius  
2. App scrapes local listings  
3. Auto-translation + condition parsing  
4. eBay sold-history estimation (future integration)  
5. Travel-cost estimation  
6. Demand score calculation  
7. Output formatted Smart Listing Cards  

---

## 🧪 Example Output

For an item priced at **$120 locally**:

- eBay sold-price avg: **$185**
- Demand Score: **High**
- Travel Cost: **$6.20**
- Recommended Buy Range: **$90–$110**
- Status: **Profitable Flip**

---

## 📘 Skills Demonstrated
- Python application development  
- Web scraping (Craigslist / Marketplace)  
- REST API design  
- Data cleaning & normalization  
- Translation + basic NLP  
- Scoring algorithms  
- Streamlit UI design  
- Practical automation for real-world workflows  
- GitHub documentation & project structure  

---

## 🚧 Roadmap
- [ ] Full eBay OAuth2 integration  
- [ ] Facebook Marketplace API alternative  
- [ ] Image similarity scoring  
- [ ] Historical price graphs  
- [ ] Export to CSV  
- [ ] Automated deal alert emails  
- [ ] Mobile-friendly UI  

---

## 📄 License
MIT License
