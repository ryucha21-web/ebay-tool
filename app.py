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
if 'current_raw_data' not in st.session_state:
    st.session_state.current_raw_data = None # スクレイピング直後の生データ
if 'selected_image_indices' not in st.session_state:
    st.session_state.selected_image_indices = []

# --- カテゴリー定義 (ここでItem Specificsを管理) ---
CATEGORY_CONFIG = {
    "Collectibles (Figures/Toys)": {
        "id": "246",
        "specifics": ["Brand", "Franchise", "Character", "Type", "Year"]
    },
    "Clothing/Shoes (Sneakers)": {
        "id": "15709", # Men's Shoes
        "specifics": ["Brand", "US Shoe Size", "Department", "Style", "Color", "Upper Material", "Type"]
    },
    "Clothing (Apparel)": {
        "id": "1059", # Men's Clothing
        "specifics": ["Brand", "Size", "Size Type", "Department", "Color", "Type", "Style"]
    },
    "Cameras & Photo": {
        "id": "31388", # Digital Cameras
        "specifics": ["Brand", "Model", "Type", "Maximum Resolution", "Series"]
    },
    "Watches": {
        "id": "31387",
        "specifics": ["Brand", "Department", "Type", "Model", "Movement", "Dial Color"]
    },
    "Fishing (Reels/Rods)": {
        "id": "1492",
        "specifics": ["Brand", "Reel Type", "Hand Retrieve", "Fish Species", "Model"]
    },
    "Video Games": {
        "id": "139973",
        "specifics": ["Platform", "Game Name", "Publisher", "Region Code", "Rating"]
    },
    "Others (Generic)": {
        "id": "1",
        "specifics": ["Brand", "MPN", "Type", "Model"]
    }
}

# --- 共通関数 ---
def translate_text(text):
    try:
        if not text or text == "取得失敗": return ""
        return GoogleTranslator(source='ja', target='en').translate(text)
    except:
        return text

# --- スクレイピングロジック (前回同様の強力版) ---
async def scrape_data(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")
        page = await context.new_page()
        
        try:
            await page.goto(url, timeout=60000)
            try: await page.wait_for_load_state("domcontentloaded", timeout=10000)
            except: pass
            await page.wait_for_timeout(3000)

            # 画像取得ロジック (サイト共通)
            image_urls = []
            
            # 1. Amazon/Mercari/Yahoo/Rakutenごとの特有処理
            if "mercari" in url:
                imgs = await page.locator("img").all()
                for img in imgs:
                    src = await img.get_attribute("src")
                    if src and "static.mercdn.net/item/detail/orig/photos/" in src:
                        image_urls.append(src.split('?')[0])
            
            elif "yahoo" in url:
                imgs = await page.locator("img").all()
                for img in imgs:
                    src = await img.get_attribute("src")
                    if src and "auctions.c.yimg.jp/images/" in src:
                        image_urls.append(src.split('?')[0])
            
            elif "rakuten" in url:
                imgs = await page.locator("img").all()
                for img in imgs:
                    src = await img.get_attribute("src")
                    if src and ("tshop.r10s.jp" in src or "cabinet" in src):
                        if not any(x in src for x in ["logo", "banner", "icon"]):
                            image_urls.append(src.split('?')[0])
            
            elif "amazon" in url:
                imgs = await page.locator("img").all()
                for img in imgs:
                    src = await img.get_attribute("src")
                    if src and ("m.media-amazon.com/images/I/" in src or "ssl-images-amazon.com" in src):
                        image_urls.append(src.split('._')[0] + '.jpg')
            
            # 2. 汎用フォールバック (og:image)
            if not image_urls:
                meta_img = page.locator("meta[property='og:image']")
                if await meta_img.count() > 0:
                    image_urls.append(await meta_img.get_attribute("content"))

            # 重複排除
            image_urls = list(dict.fromkeys(image_urls))

            # テキスト取得
            title = ""
            meta_title = page.locator("meta[property='og:title']")
            if await meta_title.count() > 0:
                title = await meta_title.get_attribute("content")
            if not title:
                if await page.locator("h1").count() > 0:
                    title = await page.locator("h1").first.inner_text()
            
            price = "0"
            # 簡易価格取得
            body_text = await page.inner_text("body")
            # "¥10,000" のようなパターンを探す簡易正規表現
            prices = re.findall(r'[¥￥][\d,]+', body_text)
            if prices:
                price = prices[0] # 最初に見つかった価格を採用

            desc = ""
            meta_desc = page.locator("meta[property='og:description']")
            if await meta_desc.count() > 0:
                desc = await meta_desc.get_attribute("content")

            return {"title": title, "price": price, "description": desc, "images": image_urls}

        except Exception as e:
            return {"error": str(e)}
        finally:
            await browser.close()

# --- 画面UI設定 ---
st.set_page_config(layout="wide")
st.title("eBay出品アシスタント (手出品 & CSV対応版)")

# --- サイドバー設定 ---
st.sidebar.header("共通設定")
usd_rate = st.sidebar.number_input("為替レート ($1=¥)", value=150)
target_profit = st.sidebar.number_input("目標利益 (¥)", value=2000)
ebay_fee_rate = 0.15 

# カテゴリー選択
selected_cat_name = st.sidebar.selectbox("出品カテゴリーを選択", list(CATEGORY_CONFIG.keys()))
cat_config = CATEGORY_CONFIG[selected_cat_name]

# --- メインエリア ---
url = st.text_input("商品URL (メルカリ, ヤフオク, 楽天, Amazon)", "")

if st.button("情報を取得する"):
    if not url:
        st.warning("URLを入力してください")
    else:
        with st.spinner('解析中...'):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            raw_data = loop.run_until_complete(scrape_data(url))
            loop.close()
            
            if "error" in raw_data:
                st.error(f"エラー: {raw_data['error']}")
            else:
                # 生データをセッションに保存
                st.session_state.current_raw_data = raw_data
                # 初期状態では全画像を選択状態にする
                st.session_state.selected_image_indices = list(range(len(raw_data['images'])))

# --- データ編集画面 ---
if st.session_state.current_raw_data:
    raw = st.session_state.current_raw_data
    
    st.markdown("---")
    st.subheader("1. 画像の選別")
    st.caption("不要な画像のチェックを外してください")

    # 画像選別グリッド
    imgs = raw['images']
    cols = st.columns(6) # 6列で表示
    selected_indices = []
    
    # 画像ごとにチェックボックスを表示
    for i, img_url in enumerate(imgs):
        with cols[i % 6]:
            st.image(img_url, use_container_width=True)
            # keyを一意にする
            is_checked = st.checkbox(f"画像 {i+1}", value=(i in st.session_state.selected_image_indices), key=f"img_chk_{i}")
            if is_checked:
                selected_indices.append(i)
    
    # 選択状態を更新
    st.session_state.selected_image_indices = selected_indices
    final_images = [imgs[i] for i in selected_indices]

    st.markdown("---")
    st.subheader("2. 出品データ編集 (手出品モード)")
    
    # 翻訳と計算 (初回のみ実行されるようにしたいが、シンプルさ優先で毎回計算)
    title_en = translate_text(raw['title'])
    desc_en = translate_text(raw['description'][:800]) # 長すぎ防止
    
    try:
        price_str = str(raw['price']).replace(',', '').replace('円', '').replace('￥', '')
        price_jp = int(re.search(r'\d+', price_str).group())
        price_usd = (price_jp + target_profit) / usd_rate / (1 - ebay_fee_rate)
        price_usd = round(price_usd, 2)
    except:
        price_jp = 0
        price_usd = 0.00

    # --- 左右分割レイアウト ---
    left_col, right_col = st.columns([1, 1])

    with left_col:
        st.info("🖼️ 選んだ画像 (上から順)")
        # 選択された画像を縦に並べる（ドラッグ&ドロップはStreamlit標準では不可だが、一覧性は高い）
        for i, img_url in enumerate(final_images):
            st.image(img_url, width=300, caption=f"No.{i+1}")
            st.text_input(f"URL {i+1} (Copy用)", value=img_url, key=f"url_copy_{i}")

    with right_col:
        st.info("📝 Item Specifics & 詳細")
        
        with st.form("listing_form"):
            # 基本情報
            new_title = st.text_input("Title (80文字)", value=title_en, max_chars=80)
            new_price = st.number_input("Start Price ($)", value=price_usd)
            new_desc = st.text_area("Description (HTML可)", value=desc_en, height=200)
            
            st.markdown("### Item Specifics")
            specifics_values = {}
            
            # カテゴリー設定に基づいた入力欄を生成
            for spec in cat_config["specifics"]:
                # タイトルからそれっぽい値を推測して初期値に入れる（簡易版）
                default_val = ""
                if spec == "Brand":
                    # 簡易ブランド検知
                    for b in ["Nike", "Adidas", "Sony", "Canon", "Nikon", "Shimano", "Daiwa", "Seiko", "Casio", "Nintendo", "Bandai"]:
                        if b.lower() in new_title.lower():
                            default_val = b
                            break
                
                specifics_values[spec] = st.text_input(spec, value=default_val)

            submitted = st.form_submit_button("リストに追加 & CSV準備")

            if submitted:
                # 保存用データ作成
                item_data = {
                    "Action": "Add",
                    "Category": cat_config["id"],
                    "Title": new_title,
                    "StartPrice": new_price,
                    "Description": new_desc,
                    "ConditionID": "3000",
                    "PicURL": "|".join(final_images) # 選択された画像のみ結合
                }
                # Specificsを結合
                item_data.update(specifics_values)
                
                st.session_state.scraped_data_list.append(item_data)
                st.success("リストに追加しました！")

# --- リストとCSV出力 ---
st.markdown("---")
st.subheader(f"📂 出品待ちリスト ({len(st.session_state.scraped_data_list)}件)")

if st.session_state.scraped_data_list:
    df = pd.DataFrame(st.session_state.scraped_data_list)
    
    # 優先表示カラム
    priority_cols = ["Title", "StartPrice", "PicURL"] + cat_config["specifics"]
    # 存在しないカラムを除外
    display_cols = [c for c in priority_cols if c in df.columns]
    
    st.dataframe(df[display_cols])
    
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 CSVをダウンロード (eBay File Exchange形式)",
        data=csv,
        file_name='ebay_listing_final.csv',
        mime='text/csv',
    )
