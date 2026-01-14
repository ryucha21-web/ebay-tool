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
        # 簡易チェックしてインストール
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    except Exception as e:
        print(f"Error installing browser: {e}")

install_playwright_browser()

from playwright.async_api import async_playwright
from deep_translator import GoogleTranslator

# --- Windows対策 ---
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# --- セッション状態の初期化 ---
if 'scraped_data_list' not in st.session_state:
    st.session_state.scraped_data_list = []

# --- 便利な関数たち ---

def translate_text(text):
    """日本語→英語翻訳"""
    try:
        return GoogleTranslator(source='ja', target='en').translate(text)
    except:
        return text

def extract_hobby_brand(text):
    """ホビー・ゲーム系の主要ブランド抽出"""
    # 日本の主要メーカーリスト
    brands = [
        "Bandai", "Banpresto", "Nintendo", "Sony", "Sega", "Pokemon", 
        "Sanrio", "Konami", "Takara Tomy", "Good Smile Company", 
        "Kotobukiya", "Tamiya", "Square Enix", "Capcom", "Funko"
    ]
    text_lower = text.lower()
    for brand in brands:
        if brand.lower() in text_lower:
            return brand
    return "Unbranded" # または空欄

def guess_type(text):
    """タイトルから商品タイプを簡易推測"""
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
        return "Action Figure" # デフォルト

# --- スクレイピング処理 ---
async def scrape_data(url):
    async with async_playwright() as p:
        # ヘッドレスモード設定
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        page = await browser.new_page()
        try:
            await page.goto(url, timeout=60000)
            try:
                await page.wait_for_selector("h1", state="visible", timeout=30000)
            except:
                pass
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
            
            image_url = ""
            meta_img = page.locator("meta[property='og:image']")
            if await meta_img.count() > 0:
                image_url = await meta_img.get_attribute("content")

            return {"title": title, "price": price, "description": desc, "image_url": image_url}
        except Exception as e:
            return {"error": str(e)}
        finally:
            await browser.close()

# --- 画面UI ---
st.set_page_config(layout="wide")
st.title("eBay出品ツール (コレクティブルズ/ホビー版)")

# サイドバー設定
st.sidebar.header("設定")
usd_rate = st.sidebar.number_input("為替レート (1ドル=〇〇円)", value=150)
target_profit = st.sidebar.number_input("目標利益 (円)", value=2000)
ebay_fee_rate = 0.15 

url = st.text_input("メルカリの商品URL (フィギュア・ゲーム・トレカ等)", "")

if st.button("情報を取得して変換"):
    if not url:
        st.warning("URLを入力してください")
    else:
        with st.spinner('ホビー情報を解析中...'):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            data = loop.run_until_complete(scrape_data(url))
            loop.close()
            
            if "error" in data:
                st.error(f"エラー: {data['error']}")
            else:
                # 翻訳
                title_en = translate_text(data['title'])
                desc_en = translate_text(data['description'][:500])
                
                # ホビー特化の推測ロジック
                brand_val = extract_hobby_brand(title_en + " " + data['title'])
                type_val = guess_type(title_en + " " + data['title'])
                
                # 価格計算
                try:
                    price_jp = int(re.sub(r'[^\d]', '', data['price']))
                    price_usd = (price_jp + target_profit) / usd_rate / (1 - ebay_fee_rate)
                    price_usd = round(price_usd, 2)
                except:
                    price_jp = 0
                    price_usd = 0.00

                # 一時保存データ作成
                st.session_state.current_data = {
                    "Action": "Add",
                    "Category": "246", # Action FiguresのID (仮)
                    "Title": title_en,
                    "StartPrice": price_usd,
                    "ConditionID": "3000", # Used
                    "Description": desc_en,
                    "PicURL": data['image_url'],
                    
                    # --- Collectibles 必須4項目 ---
                    "Brand": brand_val,
                    "Type": type_val,
                    "Franchise": "", # 作品名（手入力推奨）
                    "Character": "", # キャラ名（手入力推奨）
                }
                
                # 画面表示
                col1, col2 = st.columns(2)
                with col1:
                    if data['image_url']: st.image(data['image_url'], width=200)
                    st.write(f"🇯🇵 仕入: ¥{price_jp}")
                    st.caption(data['title'])
                
                with col2:
                    st.success(f"🇺🇸 出品: ${price_usd}")
                    st.info("作品名(Franchise)とキャラ名(Character)を入力してください")

# フォームエリア
if 'current_data' in st.session_state:
    st.markdown("### 🤖 Item Specifics (ホビー・グッズ用)")
    with st.form("edit_form"):
        c_data = st.session_state.current_data
        
        # タイトルと価格
        col_a, col_b = st.columns([3, 1])
        new_title = col_a.text_input("Title (80文字以内)", c_data['Title'], max_chars=80)
        new_price = col_b.number_input("Price ($)", value=c_data['StartPrice'])
        
        st.markdown("---")
        st.caption("Required Item Specifics (必須項目)")
        
        # コレクティブルズ用入力欄
        r1, r2 = st.columns(2)
        new_franchise = r1.text_input("Franchise (作品・シリーズ名)", c_data['Franchise'], placeholder="例: Dragon Ball Z, Pokemon, One Piece")
        new_character = r2.text_input("Character (キャラクター名)", c_data['Character'], placeholder="例: Son Goku, Pikachu, Luffy")
        
        r3, r4 = st.columns(2)
        new_brand = r3.text_input("Brand (メーカー)", c_data['Brand'])
        new_type = r4.text_input("Type (種類)", c_data['Type'])

        # データ更新と保存
        submitted = st.form_submit_button("リストに追加する")
        
        if submitted:
            c_data['Title'] = new_title
            c_data['StartPrice'] = new_price
            c_data['Brand'] = new_brand
            c_data['Franchise'] = new_franchise
            c_data['Character'] = new_character
            c_data['Type'] = new_type
            
            st.session_state.scraped_data_list.append(c_data)
            st.success("✅ リストに追加しました！")

# リスト表示エリア
st.markdown("---")
st.subheader(f"📂 出品待ちリスト ({len(st.session_state.scraped_data_list)}件)")

if st.session_state.scraped_data_list:
    df = pd.DataFrame(st.session_state.scraped_data_list)
    
    # 重要な列を左に
    cols = ["Title", "StartPrice", "Franchise", "Character", "Brand", "Type", "PicURL"]
    existing_cols = [c for c in cols if c in df.columns]
    remaining_cols = [c for c in df.columns if c not in existing_cols]
    df = df[existing_cols + remaining_cols]

    st.dataframe(df)
    
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 CSVをダウンロード",
        data=csv,
        file_name='ebay_collectibles.csv',
        mime='text/csv',
    )
