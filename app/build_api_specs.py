"""
build_api_specs.py
-----------------------------------
Scrapes the FinPerf documentation website using headless Selenium,
visits each route, collects text, and uses an LLM to extract
structured API specifications into finperf_api_specs.json.

Output format:
{
  "apis": [
    {
      "name": "calculate_sharpe",
      "route": "/analytics/sharpe",
      "method": "POST",
      "description": "...",
      "parameters": [...],
      "validation_rules": {...},
      "keywords": ["..."]
    },
    ...
  ]
}
"""

import os
import json
import time
import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

from app.llm_client import call_groq  # <- must work in your environment
from pymongo import MongoClient
from app.config import MONGO_URL


# ==============================================
#  Scraping FinPerf Documentation
# ==============================================

def scrape_all_routes(base_url: str = "https://finperf-docs.lovable.app/") -> dict:
    """
    Use headless Chrome to crawl all documentation routes and collect text content.
    Returns: dict {route_path: page_text}
    """
    print(f"🚀 Starting scrape for {base_url}")

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")

    driver = webdriver.Chrome(options=options)
    driver.get(base_url)
    time.sleep(3)

    routes = set(["/"])
    route_text_map = {}

    # Collect links from homepage
    links = driver.find_elements(By.TAG_NAME, "a")
    for link in links:
        href = link.get_attribute("href")
        if href and href.startswith(base_url):
            rel = href.replace(base_url, "/")
            rel = "/" + rel.strip("/")
            routes.add(rel)

    print(f"🔗 Found {len(routes)} routes")

    # Visit each route and extract text
    for route in sorted(routes):
        try:
            url = urljoin(base_url, route)
            driver.get(url)
            time.sleep(2)
            body_text = driver.find_element(By.TAG_NAME, "body").text.strip()
            route_text_map[route] = body_text
            print(f"✅ Fetched {route}, {len(body_text)} chars")
        except Exception as e:
            print(f"⚠️ Failed to fetch {route}: {e}")

    driver.quit()
    print(f"📘 Total routes scraped: {len(route_text_map)}")
    return route_text_map


# ==============================================
#  LLM Extraction per Route
# ==============================================

def extract_apis_from_docs(route_text_map: dict) -> dict:
    """
    For each route's text, ask the LLM to extract structured API metadata.
    Returns: { "apis": [...] }
    """
    all_apis = []

    for route, content in route_text_map.items():
        if route == "/":
            continue  # Skip homepage
        print(f"🔍 Extracting APIs from {route} ...")

        prompt = f"""
        You are an API documentation parser.

        Analyze the following FinPerf documentation section.
        Extract every API endpoint and its details in structured JSON.

        Route: {route}
        Content:
        {content}

        Respond in valid JSON:
        {{
          "apis": [
            {{
              "name": "api_name",
              "route": "/api/path",
              "method": "GET or POST",
              "description": "brief summary",
              "parameters": [
                {{"name": "param_name", "type": "string", "required": true, "description": "..."}}
              ],
              "validation_rules": {{
                "param_name": "rule text if any"
              }},
              "keywords": ["keyword1", "keyword2"]
            }}
          ]
        }}
        """

        try:
            llm_output = call_groq("", prompt)
            cleaned = re.sub(r"^```(?:json)?|```$", "", llm_output.strip())
            parsed = json.loads(cleaned)
            apis = parsed.get("apis", [])
            if apis:
                for api in apis:
                    api["source_route"] = route
                all_apis.extend(apis)
                print(f"✅ Extracted {len(apis)} APIs from {route}")
            else:
                print(f"⚠️ No APIs found in {route}")
        except Exception as e:
            print(f"❌ Failed to parse {route}: {e}")

    return {"apis": all_apis}


# ==============================================
#  Main entrypoint
# ==============================================
def save_specs_to_mongo(apis):
    collection = get_mongo_collection()
    if collection is not None:
        collection.update_one(
            {"type": "specs"},
            {"$set": {"apis": apis}},
            upsert=True
        )

def get_mongo_collection():
    try:
        client = MongoClient(MONGO_URL)
        db = client["finperf"]
        return db["api_specs"]
    except Exception as e:
        print(f"MongoDB connection failed: {e}")
        return None
        
def build_api_specs():
    route_text_map = scrape_all_routes()
    specs = extract_apis_from_docs(route_text_map)

    # Fetch all names from data APIs
    from app.config import DATA_API_URL
    import requests
    portfolio_names = []
    benchmark_names = []
    try:
        resp = requests.get(f"{DATA_API_URL}/portfolios")
        if resp.status_code == 200:
            portfolio_names = resp.json().get("names", [])
    except Exception as e:
        print(f"Failed to fetch portfolio names: {e}")
    try:
        resp = requests.get(f"{DATA_API_URL}/benchmarks")
        if resp.status_code == 200:
            benchmark_names = resp.json().get("names", [])
    except Exception as e:
        print(f"Failed to fetch benchmark names: {e}")

    # Save everything to Mongo
    collection = get_mongo_collection()
    if collection is not None:
        collection.update_one(
            {"type": "specs"},
            {"$set": {
                "apis": specs["apis"],
                "portfolio_names": portfolio_names,
                "benchmark_names": benchmark_names
            }},
            upsert=True
        )

    print(f"Successfully built API specs with {len(specs['apis'])} endpoints, {len(portfolio_names)} portfolios, {len(benchmark_names)} benchmarks.")


if __name__ == "__main__":
    build_api_specs()
