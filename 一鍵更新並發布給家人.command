#!/bin/bash
cd "$(dirname "$0")"
echo "=================================================="
echo "🚀 正在更新市場傳導輪最新行情與突發新聞..."
echo "=================================================="
python3 update_market_engine.py
echo ""
echo "🎉 更新與雲端同步完成！家人手機打開即可看見最新內容。"
echo "專屬雲端網址：https://john19831010-jpg.github.io/market-transmission-graph/"
echo "（本視窗可隨時關閉）"
