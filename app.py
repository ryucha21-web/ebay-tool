import streamlit as st
import asyncio
import sys
import subprocess
import pandas as pd
import re

# --- ブラウザインストール処理 ---
def install_playwright_browser():
    try:
        import os
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    except Exception as e:
        print(f"Error installing browser: {e}")

install_playwright_browser()

from playwright.async_api import async_playwright
from deep_translator import GoogleTranslator

# --- Windows対策 ---
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# --- セッション初期化 ---
if 'scraped_data_list' not in st.session_state:
    st.session_state.scraped_data_list = []

# --- 共通関数 ---
def translate_text(text):
    try:
        if not text or text == "取得失敗": return ""
        return GoogleTranslator(source='ja', target='en').translate(text)
    except:
        return text

def extract_hobby_brand(text):
    brands = [
        "Bandai", "Banpresto", "Nintendo", "Sony", "Sega", "Pokemon", 
        "Sanrio", "Konami", "Takara Tomy", "Good Smile Company", 
        "Kotobukiya", "Tamiya", "Square Enix", "Capcom", "Funko", "Lego", "Mattel"
    ]
    text_lower = text.lower()
    for brand in brands:
        if brand.lower() in text_lower:
            return brand
    return "Unbranded"

def guess_type(text):
    text_lower = text.lower()
    if "figure" in text_lower or "フィギュア" in text_lower:
        return "Action Figure"
    elif "plush" in text_lower or "ぬいぐるみ" in text_lower or "doll" in text_lower:
        return "Plush"
    elif "card" in text_lower or "tcg" in text_lower:
        return "Trading Card"
    elif "game" in text_lower or "console" in text_lower:
        return "Video Game"
    else:
        return "Action Figure"

# --- サイト別スクレイピングロジック ---

async def scrape_mercari_logic(page):
    """メルカリ専用ロジック"""
    images_elements = await page.locator("img").all()
    image_urls = []
    seen = set()
    for img in images_elements:
        src = await img.get_attribute("src")
        if src and "static.mercdn.net/item/detail/orig/photos/" in src:
            clean = src.split('?')[0]
            if clean not in seen:
                image_urls.append(clean)
                seen.add(clean)
    
    title = await page.locator("h1").first.inner_text()
    
    price = "0"
    if await page.locator("[data-testid='price']").count() > 0:
        price = await page.locator("[data-testid='price']").first.inner_text()
    
    desc = ""
    if await page.locator("[data-testid='description']").count() > 0:
        desc = await page.locator("[data-testid='description']").first.inner_text()
        
    return {"title": title, "price": price, "description": desc, "images": image_urls}

async def scrape_yahoo_logic(page):
    """ヤフオク専用ロジック"""
    images_elements = await page.locator("img").all()
    image_urls = []
    seen = set()
    for img in images_elements:
        src = await img.get_attribute("src")
        if src and "auctions.c.yimg.jp/images/" in src:
            clean = src.split('?')[0]
            if clean not in seen:
                image_urls.append(clean)
                seen.add(clean)

    title = ""
    if await page.locator("h1").count() > 0:
        title = await page.locator("h1").first.inner_text()
        
    price = "0"
    price_selectors = ["[class*='Price__value']", ".Price__value", ".Price"]
    for sel in price_selectors:
        if await page.locator(sel).count() > 0:
            price = await page.locator(sel).first.inner_text()
            break

    desc = ""
    desc_selectors = ["[class*='ProductExplanation__comment']", "#ProductExplanation"]
    for sel in desc_selectors:
        if await page.locator(sel).count() > 0:
            desc = await page.locator(sel).first.inner_text()
            break
            
    return {"title": title, "price": price, "description": desc, "images": image_urls}

async def scrape_rakuten_logic(page):
    """楽天専用ロジック"""
    images_elements = await page.locator("img").all()
    image_urls = []
    seen = set()
    for img in images_elements:
        src = await img.get_attribute("src")
        if src and ("tshop.r10s.jp" in src or "image.rakuten.co.jp" in src):
            if "cabinet" in src or "img" in src: 
                clean = src.split('?')[0]
                if clean not in seen:
                    image_urls.append(clean)
                    seen.add(clean)

    title = ""
    if await page.locator(".item_name").count() > 0:
        title = await page.locator(".item_name").first.inner_text()
    elif await page.locator("h1").count() > 0:
        title = await page.locator("h1").first.inner_text()

    price = "0"
    if await page.locator("[data-price]").count() > 0:
        price = await page.locator("[data-price]").first.get_attribute("data-price")
    elif await page.locator(".price2").count() > 0:
        price = await page.locator(".price2").first.inner_text()
    elif await page.locator("span[itemprop='price']").count() > 0:
        price = await page.locator("span[itemprop='price']").first.inner_text()

    desc = ""
    if await page.locator(".item_desc").count() > 0:
        desc = await page.locator(".item_desc").first.inner_text()
    elif await page.locator(".description").count() > 0:
        desc = await page.locator(".description").first.inner_text()

    return {"title": title, "price": price, "description": desc, "images": image_urls}

async def scrape_amazon_logic(page):
    """Amazon専用ロジック"""
    images_elements = await page.locator("img").all()
    image_urls = []
    seen = set()
    for img in images_elements:
        src = await img.get_attribute("src")
        if src and ("m.media-amazon.com/images/I/" in src or "ssl-images-amazon.com" in src):
            if clean_src := src.split('._')[0] + '.jpg':
                 if clean_src not in seen:
                    image_urls.append(clean_src)
                    seen.add(clean_src)

    title = ""
    if await page.locator("#productTitle").count() > 0:
        title = await page.locator("#productTitle").first.inner_text()

    price = "0"
    if await page.locator(".a-price .a-offscreen").count() > 0:
        price = await page.locator(".a-price .a-offscreen").first.inner_text()
    
    desc = ""
    if await page.locator("#feature-bullets").count() > 0:
        desc = await page.locator("#feature-bullets").first.inner_text()

    return {"title": title, "price": price, "description": desc, "images": image_urls}


# --- メインのスクレイピング分岐処理 ---
async def scrape_data(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")
        page = await context.new_page()
        
        try:
            await page.goto(url, timeout=60000)
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=10000)
            except:
                pass
            await page.wait_for_timeout(3000)

            if "mercari" in url:
                data = await scrape_mercari_logic(page)
                site_name = "Mercari"
            elif "yahoo" in url:
                data = await scrape_yahoo_logic(page)
                site_name = "Yahoo Auction"
            elif "rakuten" in url:
                data = await scrape_rakuten_logic(page)
                site_name = "Rakuten"
            elif "amazon" in url:
                data = await scrape_amazon_logic(page)
                site_name = "Amazon"
            else:
                title = await page.locator("h1").first.inner_text()
                image_urls = []
                meta_img = page.locator("meta[property='og:image']")
                if await meta_img.count() > 0:
                     image_urls.append(await meta_img.get_attribute("content"))
                data = {"title": title, "price": "0", "description": "", "images": image_urls}
                site_name = "Unknown Site"

            data["site"] = site_name
            return data

        except Exception as e:
            return {"error": str(e)}
        finally:
            await browser.close()

# --- 画面UI ---
st.set_page_config(layout="wide")
st.title("eBay出品ツール (4大プラットフォーム対応版)")

st.sidebar.header("設定")
usd_rate = st.sidebar.number_input("為替レート (1ドル=〇〇円)", value=150)
target_profit = st.sidebar.number_input("目標利益 (円)", value=2000)
ebay_fee_rate = 0.15 

url = st.text_input("商品URL (Mercari, Yahoo, Rakuten, Amazon)", "")

if st.button("情報を取得して変換"):
    if not url:
        st.warning("URLを入力してください")
    else:
        with st.spinner('サイトを判別して解析中...'):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            data = loop.run_until_complete(scrape_data(url))
            loop.close()
            
            if "error" in data:
                st.error(f"エラー: {data['error']}")
            else:
                st.info(f"検出されたサイト: {data['site']}")
                
                title_en = translate_text(data['title'])
                desc_en = translate_text(data['description'][:500])
                brand_val = extract_hobby_brand(title_en + " " + (data['title'] or ""))
                type_val = guess_type(title_en + " " + (data['title'] or ""))
                
                try:
                    price_str = str(data['price']).replace(',', '').replace('円', '').replace('￥', '')
                    price_jp = int(re.search(r'\d+', price_str).group())
                    price_usd = (price_jp + target_profit) / usd_rate / (1 - ebay_fee_rate)
                    price_usd = round(price_usd, 2)
                except:
                    price_jp = 0
                    price_usd = 0.00

                pic_url_str = "|".join(data['images']) if data['images'] else ""

                st.session_state.current_data = {
                    "Action": "Add",
                    "Category": "246", 
                    "Title": title_en,
                    "StartPrice": price_usd,
                    "ConditionID": "3000",
                    "Description": desc_en,
                    "PicURL": pic_url_str,
                    "Brand": brand_val,
                    "Type": type_val,
                    "Franchise": "",
                    "Character": "",
                }
                
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    st.subheader(f"📸 画像 ({len(data['images'])}枚)")
                    if data['images']:
                        cols = st.columns(4)
                        for i, img_url in enumerate(data['images'][:8]):
                            with cols[i % 4]:
                                st.image(img_url, caption=f"No.{i+1}", use_container_width=True)
                    
                    st.write(f"🇯🇵 仕入: ¥{price_jp}")
                    st.caption(data['title'])
                
                with col2:
                    st.subheader("🇺🇸 出品データ確認")
                    st.success(f"出品価格: ${price_usd}")
                    st.info("Item Specificsを入力してリストに追加してください")

if 'current_data' in st.session_state:
    st.markdown("---")
    with st.form("edit_form"):
        c_data = st.session_state.current_data
        
        col_a, col_b = st.columns([3, 1])
        new_title = col_a.text_input("Title", c_data['Title'], max_chars=80)
        new_price = col_b.number_input("Price ($)", value=c_data['StartPrice'])
        
        st.caption("Required Item Specifics")
        r1, r2 = st.columns(2)
        new_franchise = r1.text_input("Franchise", c_data['Franchise'])
        new_character = r2.text_input("Character", c_data['Character'])
        
        r3, r4 = st.columns(2)
        new_brand = r3.text_input("Brand", c_data['Brand'])
        new_type = r4.text_input("Type", c_data['Type'])

        submitted = st.form_submit_button("リストに追加する")
        
        if submitted:
            c_data['Title'] = new_title
            c_data['StartPrice'] = new_price
            c_data['Brand'] = new_brand
            c_data['Franchise'] = new_franchise
            c_data['Character'] = new_character
            c_data['Type'] = new_type
            
            st.session_state.scraped_data_list.append(c_data)
            st.success(f"✅ 追加しました！")

st.markdown("---")
st.subheader(f"📂 出品待ちリスト ({len(st.session_state.scraped_data_list)}件)")

if st.session_state.scraped_data_list:
    df = pd.DataFrame(st.session_state.scraped_data_list)
    display_df = df.copy()
    display_df['PicURL'] = display_df['PicURL'].apply(lambda x: x[:30] + "..." if len(x) > 30 else x)
    st.dataframe(display_df)
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(label="📥 CSVダウンロード", data=csv, file_name='ebay_multi_site.csv', mime='text/csv')
