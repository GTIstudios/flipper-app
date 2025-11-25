# Flipper App — Local Deals → eBay Profit Analyzer

A Streamlit application that analyzes local Craigslist and Facebook Marketplace listings and compares them to eBay market data to identify profitable flips.

The app automates reseller research by:
- Normalizing item condition  
- Translating non-English descriptions  
- Calculating travel-cost impact  
- Generating Demand Scores  
- Recommending target buy prices  
- Displaying opportunities in clean Smart Listing Cards  

Built to significantly reduce time spent on manual item research, pricing, and evaluation.

## Features

- 🔍 Local search with keyword + location  
- 🧩 Condition Auto-Parser  
- 🌍 Auto-Translate seller descriptions  
- 📊 Demand Score (local supply + pricing + rarity)  
- 🚗 Travel-Cost + fuel calculations  
- 💰 Auto-Price Recommendation based on real market behavior  
- 📌 Smart Listing Cards  
- 🔐 eBay OAuth2 “API-ready” integration (pending activation)

## Tech Stack

- Python  
- Streamlit  
- REST APIs / JSON  
- Basic Craigslist scraping  
- eBay OAuth2 (scaffold)  
