#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市場傳導輪 - 自動化資料引擎 (Market Transmission Pipeline)
功能：
1. 抓取 Google 財經與各大媒體的最新「突發非排程新聞」，並透過 NLP 關鍵字匹配傳導因子
2. 抓取 Yahoo Finance 最新即時報價 (台股、美股、黃金)
3. 動態更新傳導輪資料庫，並重新生成單一便攜版 index.html
4. 自動 Git 提交並推播至 GitHub Pages 雲端供家人手機同步使用
"""

import os
import re
import json
import ssl
import datetime
import subprocess
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "transmission_data.json")
HTML_FILE = os.path.join(BASE_DIR, "index.html")

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}

def fetch_quotes():
    """抓取核心標的最新行情與漲跌幅"""
    tickers = {
        "t_2330": ("2330.TW", "台幣"),
        "t_2308": ("2308.TW", "台幣"),
        "t_0050": ("0050.TW", "台幣"),
        "t_00935": ("00935.TW", "台幣"),
        "t_1101": ("1101.TW", "台幣"),
        "t_bank_sp": ("5876.TW", "台幣"),
        "t_bank_sinopac": ("2890.TW", "台幣"),
        "t_qqq": ("QQQ", "美元"),
        "t_voo": ("VOO", "美元"),
        "t_googl": ("GOOGL", "美元"),
        "t_tsla": ("TSLA", "美元"),
        "t_gold": ("GC=F", "美元")
    }
    
    quotes = {}
    print("[1/5] 正在抓取最新市場行情報價...")
    for tid, (symbol, currency) in tickers.items():
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d"
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, context=SSL_CTX, timeout=5) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                meta = data['chart']['result'][0]['meta']
                price = meta.get('regularMarketPrice')
                chart_prev = meta.get('chartPreviousClose')
                
                change_pct = 0.0
                if price and chart_prev and chart_prev > 0:
                    change_pct = round(((price - chart_prev) / chart_prev) * 100, 2)
                    
                quotes[tid] = {
                    "price": price,
                    "currency": currency,
                    "change_pct": change_pct
                }
        except Exception as e:
            print(f"  - 抓取 {symbol} 失敗: {e}")
            quotes[tid] = {"price": None, "currency": currency, "change_pct": 0.0}
            
    quotes["t_spacex"] = {"price": 210.0, "currency": "美元(估值)", "change_pct": 1.5}
    return quotes


def fetch_breaking_news():
    """從即時財經新聞 RSS 抓取突發事件並提取焦點"""
    queries = [
        "台積電 OR 台達電 OR 半導體",
        "FOMC OR 聯準會 OR 降息 OR CPI OR 美股",
        "特斯拉 OR SpaceX OR 馬斯克 OR Google AI",
        "黃金 OR 碳費 OR 永豐金 OR 上海商銀"
    ]
    
    news_items = []
    print("[2/5] 正在爬取即時財經新聞與突發事件...")
    
    for q in queries:
        try:
            encoded_q = urllib.parse.quote(q)
            url = f"https://news.google.com/rss/search?q={encoded_q}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, context=SSL_CTX, timeout=6) as resp:
                root = ET.fromstring(resp.read())
                for item in root.findall('./channel/item')[:5]:
                    title = item.find('title').text or ""
                    pub_date = item.find('pubDate').text or ""
                    link = item.find('link').text or ""
                    
                    clean_title = title.split(" - ")[0].strip()
                    source = title.split(" - ")[-1].strip() if " - " in title else "財經即時"
                    
                    if not any(n['title'] == clean_title for n in news_items):
                        news_items.append({
                            "title": clean_title,
                            "source": source,
                            "pub_date": pub_date,
                            "link": link
                        })
        except Exception as e:
            print(f"  - 爬取新聞組 {q} 失敗: {e}")
            
    print(f"  ✔ 成功獲取 {len(news_items)} 則最新市場焦點新聞")
    return news_items


def synthesize_transmission_data(quotes, news_list):
    """將基礎排程資料、即時突發新聞節點與即時行情融合至圖譜資料結構中"""
    print("[3/5] 正在融合圖譜傳導節點與計算敏感度...")
    
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            base_data = json.load(f)
    else:
        base_data = {"events": [], "factors": [], "targets": [], "links": []}

    for tgt in base_data.get("targets", []):
        tid = tgt["id"]
        if tid in quotes:
            tgt["price"] = quotes[tid]["price"]
            tgt["currency"] = quotes[tid]["currency"]
            tgt["change_pct"] = quotes[tid]["change_pct"]

    mapping = [
        {"keywords": ["台積電", "晶圓", "CoWoS", "先進製程"], "factor": "f_foundry", "target": "t_2330", "cat": "突發半導體"},
        {"keywords": ["台達電", "電力", "散熱", "伺服器電源"], "factor": "f_server_power", "target": "t_2308", "cat": "突發基建"},
        {"keywords": ["降息", "FOMC", "聯準會", "鮑爾", "利率"], "factor": "f_rates", "target": "t_gold", "cat": "突發總經"},
        {"keywords": ["黃金", "避險", "金價"], "factor": "f_dollar", "target": "t_gold", "cat": "突發貴金屬"},
        {"keywords": ["Google", "Gemini", "雲端", "AI模型"], "factor": "f_ai_cloud", "target": "t_googl", "cat": "突發AI"},
        {"keywords": ["特斯拉", "Robotaxi", "FSD", "馬斯克"], "factor": "f_ev_auto", "target": "t_tsla", "cat": "突發自駕"},
        {"keywords": ["SpaceX", "星鏈", "Starship", "低軌衛星"], "factor": "f_satellite", "target": "t_spacex", "cat": "突發航太"},
        {"keywords": ["碳費", "台泥", "綠能", "儲能"], "factor": "f_green_energy", "target": "t_1101", "cat": "突發ESG"},
        {"keywords": ["永豐金", "上海商銀", "銀行", "股利", "存貸"], "factor": "f_banking_spread", "target": "t_bank_sinopac", "cat": "突發金融"}
    ]
    
    used_titles = set()
    breaking_events = []
    breaking_links = []
    b_idx = 1
    
    for item in news_list:
        title = item["title"]
        for rule in mapping:
            if any(k in title for k in rule["keywords"]) and title not in used_titles:
                used_titles.add(title)
                eid = f"e_breaking_{b_idx}"
                short_name = title if len(title) <= 22 else title[:20] + "..."
                
                b_evt = {
                    "id": eid,
                    "name": f"⚡ {short_name}",
                    "date": datetime.date.today().strftime("%m-%d"),
                    "category": rule["cat"],
                    "isBreaking": True,
                    "newsTitle": title,
                    "newsSource": item["source"],
                    "newsDate": item.get("pub_date", ""),
                    "newsUrl": item.get("link", ""),
                    "desc": f"【{item['source']}】{title}",
                    "impactTargets": [rule["target"]],
                    "primaryChain": [rule["factor"], rule["target"]]
                }
                breaking_events.append(b_evt)
                
                breaking_links.append({
                    "source": eid,
                    "target": rule["factor"],
                    "weight": 92,
                    "desc": f"突發快訊即時牽動市場預期：{rule['cat']}"
                })
                
                b_idx += 1
                break
        if len(breaking_events) >= 4:
            break
            
    scheduled_events = [e for e in base_data.get("events", []) if not e.get("isBreaking", False)]
    combined_events = breaking_events + scheduled_events
    
    scheduled_links = [l for l in base_data.get("links", []) if not l.get("source", "").startswith("e_breaking_")]
    combined_links = breaking_links + scheduled_links
    
    target_hits = {}
    for l in combined_links:
        t = l["target"]
        target_hits[t] = target_hits.get(t, 0) + 1
        
    for tgt in base_data.get("targets", []):
        tid = tgt["id"]
        extra = target_hits.get(tid, 0) * 3
        tgt["score"] = min(100, tgt.get("score", 80) + extra)
        
    final_data = {
        "updatedAt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "events": combined_events,
        "factors": base_data.get("factors", []),
        "targets": base_data.get("targets", []),
        "links": combined_links
    }
    
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)
        
    return final_data


def update_html_with_embedded_data(graph_data):
    """將最新資料安全內嵌至 index.html"""
    print("[4/5] 正在更新網頁介面並內嵌最新圖譜資料...")
    with open(HTML_FILE, "r", encoding="utf-8") as f:
        html = f.read()

    json_str = json.dumps(graph_data, ensure_ascii=False, indent=2)
    
    pattern = r"const embeddedGraphData = \{.*?\n\s*\};"
    replacement = f"const embeddedGraphData = {json_str};"
    
    if re.search(pattern, html, flags=re.DOTALL):
        html = re.sub(pattern, replacement, html, flags=re.DOTALL)
    else:
        search_anchor = "// 內嵌完整資料，避免本地 file:// 協議被瀏覽器 CORS 阻擋\n    const embeddedGraphData ="
        if search_anchor in html:
            part1 = html.split(search_anchor)[0]
            after = html.split(search_anchor)[1]
            part2 = after.split(";\n\n    // 啟動視覺化")[1]
            html = f"{part1}{search_anchor} {json_str};\n\n    // 啟動視覺化{part2}"
            
    updated_str = graph_data.get("updatedAt", "")
    html = re.sub(r'id="lastUpdateBadge">.*?</span>', f'id="lastUpdateBadge">{updated_str} 實時更新</span>', html)
    
    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)
        
    print(f"  ✔ index.html 已更新至最新傳導資料！")


def sync_to_github():
    """自動提交並推播至 GitHub Pages 雲端（若在 GitHub Actions 雲端環境中則由 workflow 接管）"""
    if os.environ.get("GITHUB_ACTIONS"):
        print("[5/5] 偵測到 GitHub Actions 雲端環境，由 Workflow 接管自動提交。")
        return

    print("[5/5] 正在自動同步至 GitHub Pages 雲端...")
    try:
        subprocess.run(["git", "add", "."], cwd=BASE_DIR, check=True)
        # 檢查是否有改動
        res = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=BASE_DIR)
        if res.returncode != 0:
            commit_msg = f"Auto update market transmission: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
            subprocess.run(["git", "commit", "-m", commit_msg], cwd=BASE_DIR, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=BASE_DIR, check=True)
            print("  ✔ 成功推播至 GitHub Pages 雲端！家人手機即刻同步！")
        else:
            print("  - 資料無變更，跳過推播")
    except Exception as e:
        print(f"  - Git 推播略過或失敗: {e}")


if __name__ == "__main__":
    print("==================================================")
    print("🚀 市場傳導輪 - 每日自動爬蟲與突發新聞更新引擎啟動")
    print("==================================================")
    quotes = fetch_quotes()
    news = fetch_breaking_news()
    data = synthesize_transmission_data(quotes, news)
    update_html_with_embedded_data(data)
    sync_to_github()
    print("==================================================")
    print(f"🎉 全部完成！更新時間：{data['updatedAt']}")
    print("==================================================")
