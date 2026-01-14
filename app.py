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

# --- セッション状態の初期化 ---
if 'scraped_data_list' not in st.session_state:
    st.session_state.scraped_data_list = []

# --- 関数群 ---

def translate_text(text):
    try:
        return GoogleTranslator(source='ja', target='en').translate(text)
    except:
        return text

def extract_hobby_brand(text):
    brands = [
        "Bandai", "Banpresto", "Nintendo", "Sony", "Sega", "Pokemon", 
        "Sanrio", "Konami", "Takara Tomy", "Good Smile Company", 
        "Kotobukiya", "Tamiya", "Square Enix", "Capcom", "Funko", "Lego"
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

# --- スクレイピング処理（全画像取得版） ---
async def scrape_data(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        page = await browser.new_page()
        try:
            await page.goto(url, timeout=60000)
            try:
                await page.wait_for_selector("h1", state="visible", timeout=30000)
            except:
                pass
            await page.wait_for_timeout(2000)

            # 基本情報
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
            
            # 【変更点】全画像を取得するロジック
            image_urls = []
            
            # メルカリは data-testid="image-0", image-1... という属性がついている
            # まずは image-0 から image-19 くらいまでループして探す
            for i in range(20): 
                img_locator = page.locator(f"[data-testid='image-{i}']")
                if await img_locator.count() > 0:
                    src = await img_locator.get_attribute("src")
                    if src:
                        image_urls.append(src)
                else:
                    # 連番が途切れたら終了（ただし念のため最初の数枚が見つからない場合も考慮してbreakは慎重に）
                    if i > 0 and len(image_urls) > 0:
                        break
            
            # もし上記で見つからなければ、og:imageをフォールバックとして使う
            if not image_urls:
                meta_img = page.locator("meta[property='og:image']")
                if await meta_img.count() > 0:
                    src = await meta_img.get_attribute("content")
                    image_urls.append(src)

            return {
                "title": title, 
                "price": price, 
                "description": desc, 
                "images": image_urls # リストで返す
            }
        except Exception as e:
            return {"error": str(e)}
        finally:
            await browser.close()

# --- 画面UI ---
st.set_page_config(layout="wide")
st.title("eBay出品ツール (全画像取得 & ホビー対応版)")

# サイドバー
st.sidebar.header("設定")
usd_rate = st.sidebar.number_input("為替レート (1ドル=〇〇円)", value=150)
target_profit = st.sidebar.number_input("目標利益 (円)", value=2000)
ebay_fee_rate = 0.15 

url = st.text_input("メルカリの商品URL", "")

if st.button("情報を取得して変換"):
    if not url:
        st.warning("URLを入力してください")
    else:
        with st.spinner('全画像を解析中...'):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            data = loop.run_until_complete(scrape_data(url))
            loop.close()
            
            if "error" in data:
                st.error(f"エラー: {data['error']}")
            else:
                # 翻訳・推測
                title_en = translate_text(data['title'])
                desc_en = translate_text(data['description'][:500])
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

                # 画像リストをeBay用文字列（パイプ区切り）に変換
                # 例: url1|url2|url3
                pic_url_str = "|".join(data['images'])

                st.session_state.current_data = {
                    "Action": "Add",
                    "Category": "246", 
                    "Title": title_en,
                    "StartPrice": price_usd,
                    "ConditionID": "3000",
                    "Description": desc_en,
                    "PicURL": pic_url_str, # ここに結合したURLが入る
                    "Brand": brand_val,
                    "Type": type_val,
                    "Franchise": "",
                    "Character": "",
                }
                
                # --- 表示エリア ---
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    st.subheader(f"📸 取得画像 ({len(data['images'])}枚)")
                    # 取得した画像をタイル状に表示
                    if data['images']:
                        # 最初の4枚だけプレビュー表示（多すぎると画面埋まるため）
                        cols = st.columns(4)
                        for i, img_url in enumerate(data['images'][:4]):
                            with cols[i]:
                                st.image(img_url, use_container_width=True)
                        if len(data['images']) > 4:
                            st.caption(f"...他 {len(data['images'])-4} 枚")
                    
                    st.write(f"🇯🇵 仕入: ¥{price_jp}")
                    st.caption(data['title'])
                
                with col2:
                    st.subheader("🇺🇸 出品データ確認")
                    st.success(f"出品価格: ${price_usd}")
                    st.info("Item Specificsを入力してリストに追加してください")

# フォームエリア
if 'current_data' in st.session_state:
    st.markdown("---")
    with st.form("edit_form"):
        c_data = st.session_state.current_data
        
        col_a, col_b = st.columns([3, 1])
        new_title = col_a.text_input("Title", c_data['Title'], max_chars=80)
        new_price = col_b.number_input("Price ($)", value=c_data['StartPrice'])
        
        st.caption("Required Item Specifics")
        r1, r2 = st.columns(2)
        new_franchise = r1.text_input("Franchise (作品名)", c_data['Franchise'])
        new_character = r2.text_input("Character (キャラ名)", c_data['Character'])
        
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
            st.success(f"✅ 追加しました！（画像数: {len(c_data['PicURL'].split('|'))}枚）")

# リスト表示エリア
st.markdown("---")
st.subheader(f"📂 出品待ちリスト ({len(st.session_state.scraped_data_list)}件)")

if st.session_state.scraped_data_list:
    df = pd.DataFrame(st.session_state.scraped_data_list)
    
    # 表示用にPicURLは長すぎるのでカットして表示してもいいが、CSVには全部入る
    display_df = df.copy()
    display_df['PicURL'] = display_df['PicURL'].apply(lambda x: x[:30] + "..." if len(x) > 30 else x)
    
    st.dataframe(display_df)
    
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 CSVをダウンロード (eBay用)",
        data=csv,
        file_name='ebay_collectibles_full_images.csv',
        mime='text/csv',
    )
