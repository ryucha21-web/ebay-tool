import streamlit as st
import asyncio
import sys
import os
import subprocess

# --- サーバー起動時にブラウザを強制インストールする魔法のコード ---
def install_playwright_browser():
    # ブラウザがインストールされているか確認するための簡易チェック
    # (毎回走ると遅いので、ロックファイル等で制御するのがベストですが、今回は簡易的にtry-exceptで実装)
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        # ライブラリがない場合はインストール
        subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright"])
    
    # ブラウザ本体(Chromium)のインストール
    # 毎回実行すると重いので、エラーが出た時だけ実行するロジックにする手もありますが、
    # Streamlit Cloudの仕様上、起動時に一度実行するのが確実です。
    print("Installing Playwright browsers...")
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=False)

# アプリ起動時に一度だけ実行
install_playwright_browser()
# -------------------------------------------------------------

from playwright.async_api import async_playwright
from deep_translator import GoogleTranslator
import time
import re

# --- Windows/Linux互換性のための設定 ---
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# --- ここから下の関数は前回と同じ ---

def translate_text(text):
    try:
        return GoogleTranslator(source='ja', target='en').translate(text)
    except:
        return text

def convert_size_jp_to_us(text):
    match = re.search(r'(\d+\.?\d*)\s*cm', text, re.IGNORECASE)
    if match:
        cm_size = float(match.group(1))
        us_size = cm_size - 18 
        return f"{us_size}" 
    return ""

def extract_brand(text):
    brands = ["Nike", "Adidas", "Mizuno", "Puma", "Asics", "New Balance", "Under Armour"]
    for brand in brands:
        if brand.lower() in text.lower():
            return brand
    return ""

async def scrape_data(url):
    async with async_playwright() as p:
        # ヘッドレスモードで起動
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            await page.goto(url, timeout=60000)
            try:
                await page.wait_for_selector("h1", state="visible", timeout=30000)
            except:
                pass
            
            # 少し待機
            await page.wait_for_timeout(2000)

            title_el = page.locator("h1").first
            title = await title_el.inner_text() if await title_el.count() > 0 else "取得失敗"
            
            price = "0"
            price_el = page.locator("[data-testid='price']").first
            if await price_el.count() > 0:
                price = await price_el.inner_text()
            
            desc = ""
            desc_el = page.locator("[data-testid='description']").first
            if await desc_el.count() > 0:
                desc = await desc_el.inner_text()
            
            image_url = None
            meta_img = page.locator("meta[property='og:image']")
            if await meta_img.count() > 0:
                image_url = await meta_img.get_attribute("content")

            return {
                "title": title,
                "price": price,
                "description": desc,
                "image_url": image_url
            }
        except Exception as e:
            return {"error": str(e)}
        finally:
            await browser.close()

# --- 画面描画 ---

st.set_page_config(layout="wide")
st.title("eBay出品データ生成ツール (Cloud Ver.)")

url = st.text_input("メルカリの商品URLを貼り付けてください", "")

if st.button("情報を取得して変換"):
    if not url:
        st.warning("URLを入力してください")
    else:
        with st.spinner('サーバーで処理中...（初回は時間がかかります）'):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            data = loop.run_until_complete(scrape_data(url))
            loop.close()
            
            if "error" in data:
                st.error(f"エラーが発生しました: {data['error']}")
            else:
                title_en = translate_text(data['title'])
                desc_en = translate_text(data['description'][:500])
                brand_guess = extract_brand(title_en + " " + data['title'])
                size_guess = convert_size_jp_to_us(data['description'] + " " + data['title'])

                col1, col2 = st.columns(2)

                with col1:
                    st.subheader("🇯🇵 元データ")
                    if data['image_url']:
                        st.image(data['image_url'], width=300)
                    st.text_area("タイトル", data['title'], height=80)
                    st.write(f"価格: {data['price']}")

                with col2:
                    st.subheader("🇺🇸 eBayデータ")
                    st.text_input("Title (En)", value=title_en)
                    c1, c2 = st.columns(2)
                    with c1:
                        st.text_input("Brand", value=brand_guess)
                    with c2:
                        st.text_input("US Size", value=size_guess)
                    st.text_input("Condition", value="Pre-owned")
                    st.text_area("Description (En)", value=desc_en, height=200)
                    st.success("完了！")
