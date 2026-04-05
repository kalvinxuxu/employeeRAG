#!/bin/bash
# Streamlit 应用重启脚本

cd /root/myapp
source venv/bin/activate
pkill -f streamlit || true
sleep 2
nohup streamlit run app.py --server.port=8501 --server.address=0.0.0.0 > app.log 2>&1 &
echo "应用已重启，访问地址：http://$(curl -s ifconfig.me):8501"
echo "查看日志：tail -f app.log"
