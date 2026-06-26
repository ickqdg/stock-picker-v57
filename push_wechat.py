"""
微信推送脚本 - 使用 Server酱
将选股结果推送到微信
"""

import json
import os
import requests
import sys


def send_wechat_message(title, content):
    """
    使用 Server酱 发送微信消息
    需要在环境变量中设置 SERVERCHAN_KEY
    """
    
    serverchan_key = os.environ.get('SERVERCHAN_KEY')
    
    if not serverchan_key:
        print("错误：未设置 SERVERCHAN_KEY 环境变量")
        print("请先注册 Server酱 并获取 key")
        print("注册地址：https://sct.ftqq.com/")
        return False
    
    url = f"https://sctapi.ftqq.com/{serverchan_key}.send"
    
    data = {
        'title': title,
        'desp': content
    }
    
    try:
        response = requests.post(url, data=data)
        result = response.json()
        
        if result.get('code') == 0:
            print("微信推送成功！")
            return True
        else:
            print(f"微信推送失败：{result.get('message', '未知错误')}")
            return False
            
    except Exception as e:
        print(f"微信推送异常：{e}")
        return False


def format_message(result):
    """格式化选股结果为消息内容"""
    
    date = result.get('date', '未知日期')
    market_ok = result.get('market_ok', True)
    
    if not market_ok:
        title = f"📉 V5.7操盘提醒 - {date}"
        content = f"""
## 今日操盘提醒

**日期**：{date}

**大盘状态**：❌ 观望（大盘在MA20以下）

**操作建议**：空仓观望，不硬做

---
*V5.7 双因子策略自动推送*
"""
        return title, content
    
    signal = result.get('signal')
    
    if not signal:
        title = f"⏸️ V5.7操盘提醒 - {date}"
        content = f"""
## 今日操盘提醒

**日期**：{date}

**大盘状态**：✅ 做多

**选股结果**：今天没有符合条件的股票

**操作建议**：空仓观望，等待机会

---
*V5.7 双因子策略自动推送*
"""
        return title, content
    
    # 有选股信号
    code = signal.get('code', '')
    name = signal.get('name', '')
    score = signal.get('score', 0)
    close = signal.get('close', 0)
    stop_loss = signal.get('stop_loss', 0)
    take_profit = signal.get('take_profit', 0)
    hold_days = signal.get('hold_days', 6)
    
    breakout = signal.get('breakout_20', 0)
    pullback = signal.get('pullback_pct', 0)
    vol_dec = signal.get('vol_decrease', 0)
    days_high = signal.get('days_since_high', 0)
    turn = signal.get('turn', 0)
    amplitude = signal.get('amplitude', 0)
    
    title = f"🚀 V5.7操盘提醒 - {name}({code})"
    
    content = f"""
## 今日操盘明细

**日期**：{date}

**股票**：{name}（{code}）
**评分**：{score} 分 ⭐
**昨日收盘**：{close:.2f} 元

---

### 📊 买卖计划

| 项目 | 价格 | 幅度 |
|------|------|------|
| **买入** | 开盘价 | 高开>2%放弃 |
| **止损** | {stop_loss:.2f} 元 | **-2.5%** |
| **止盈** | {take_profit:.2f} 元 | **+30%** |
| **持股** | {hold_days} 个交易日 | 到点就卖 |

**移动止盈**：盈利>5%后保本（止损上移到成本价）

---

### 📈 选股依据

| 指标 | 数值 |
|------|------|
| 突破因子 | {breakout:.2%}（接近20日新高） |
| 回调幅度 | {pullback:.2%} |
| 回调天数 | {days_high} 天 |
| 缩量程度 | {vol_dec:.2%} |
| 换手率 | {turn:.2%} |
| 振幅 | {amplitude:.2%} |

---

### ⚠️ 操盘纪律

1. **严格按开盘价买入**，高开>2%放弃
2. **严格止损**，到止损价立刻卖，不扛单
3. **到止盈价立刻卖**，不贪多
4. **持股6天**，到时间就卖，不恋战
5. **大盘不好就空仓**，不硬做

---

### 📋 备选股票
"""
    
    # 添加备选股票
    alternatives = result.get('alternatives', [])
    if alternatives:
        for i, alt in enumerate(alternatives[:5], 1):
            content += f"{i}. {alt['name']}（{alt['code']}）- {alt['score']}分 - {alt['close']:.2f}元\n"
    else:
        content += "暂无备选股票\n"
    
    content += """
---
*V5.7 双因子策略自动推送 | 投资有风险，入市需谨慎*
"""
    
    return title, content


def main():
    print('=' * 50)
    print('微信推送 - V5.7选股结果')
    print('=' * 50)
    print()
    
    # 读取结果文件
    result_file = 'result.json'
    if not os.path.exists(result_file):
        print(f"错误：找不到 {result_file}")
        print("请先运行选股脚本生成结果")
        sys.exit(1)
    
    with open(result_file, 'r', encoding='utf-8') as f:
        result = json.load(f)
    
    print(f"读取结果文件成功：{result.get('date', '未知日期')}")
    print()
    
    # 格式化消息
    title, content = format_message(result)
    
    print(f"消息标题：{title}")
    print()
    
    # 发送消息
    success = send_wechat_message(title, content)
    
    if success:
        print("\n✅ 推送完成！请查看微信")
    else:
        print("\n❌ 推送失败！")
        sys.exit(1)


if __name__ == '__main__':
    main()
