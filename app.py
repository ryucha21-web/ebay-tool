import streamlit as st
from playwright.async_api import async_playwright # 【変更】async_apiを使う
from deep_translator import GoogleTranslator
import time
import re
import asyncio # 【追加】非同期処理用
import sys

# --- Windows対策: イベントループの設定 ---
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# --- 関数定義 ---

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

# 【変更】非同期関数(async)に変更
async def scrape_data(url):
    """メルカリから情報を抜く関数（非同期版）"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True) # awaitをつける
        page = await browser.new_page()
        # await page.set_extra_http_headers({"User-Agent": "Mozilla/5.0"}) 
        # ※メルカリ等でヘッダー設定がエラーの原因になることがあるため一旦シンプルに

        try:
            # タイムアウト等の設定
            await page.goto(url, timeout=60000)
            
            # タイトルが出るまで待つ
            try:
                await page.wait_for_selector("h1", state="visible", timeout=30000)
            except:
                pass # タイムアウトしても一旦進む

            await page.wait_for_timeout(2000) # time.sleepの代わり

            # データ取得（awaitが必要な箇所と不要な箇所がある）
            # inner_text()などはawaitが必要
            
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

# --- 画面描画（UI） ---

st.set_page_config(layout="wide")
st.title("eBay出品データ生成ツール (Alpha Ver.)")

url = st.text_input("メルカリの商品URLを貼り付けてください", "")

if st.button("情報を取得して変換"):
    if not url:
        st.warning("URLを入力してください")
    else:
        with st.spinner('スクレイピング＆翻訳中...'):
            
            # 【変更】非同期関数を無理やり実行するための魔法の記述
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            data = loop.run_until_complete(scrape_data(url))
            loop.close()
            
            if "error" in data:
                st.error(f"エラーが発生しました: {data['error']}")
            else:
                # 2. データ変換（ここは今まで通り）
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