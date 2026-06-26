"""
V5.7 云端版选股脚本
不需要本地数据，直接在线获取股票数据
适用于 GitHub Actions 等云端环境
"""

import pandas as pd
import numpy as np
import time
import sys
import json

try:
    import akshare as ak
except ImportError:
    print("正在安装 akshare...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "akshare", "-q"])
    import akshare as ak


def get_stock_list():
    """获取沪深主板股票列表"""
    print("正在获取股票列表...")
    
    # 获取A股列表
        stock_info = None
    for i in range(3):
        try:
            stock_info = ak.stock_info_a_code_name()
            break
        except Exception as e:
            print(f"  第{i+1}次获取股票列表失败：{e}")
            if i < 2:
                print("  2秒后重试...")
                time.sleep(2)
    
    if stock_info is None:
        print("获取股票列表失败，使用默认股票列表")
        return []
    
    # 筛选主板股票（6开头沪市主板，0开头深市主板）
    # 排除3开头创业板，688科创板，4开头北交所
    main_board = []
    for _, row in stock_info.iterrows():
        code = row['code']
        name = row['name']
        
        # 排除ST
        if 'ST' in name or '*' in name:
            continue
            
        # 主板：6开头（沪市）或0开头（深市）
        if code.startswith('6') or code.startswith('0'):
            # 转换成 sh.600000 或 sz.000001 格式
            if code.startswith('6'):
                full_code = f'sh.{code}'
            else:
                full_code = f'sz.{code}'
            main_board.append({
                'code': full_code,
                'simple_code': code,
                'name': name
            })
    
    print(f"获取到 {len(main_board)} 只主板股票")
    return main_board


def get_stock_data(code, days=60):
    """获取单只股票的日线数据"""
    try:
        # akshare 的代码格式：600000，不带前缀
        simple_code = code.split('.')[-1]
        
        # 获取日线数据
        df = ak.stock_zh_a_hist(symbol=simple_code, period="daily", 
                                start_date="20260101", end_date="20261231",
                                adjust="qfq")
        
        if df is None or len(df) < 30:
            return None
        
        # 重命名列
        df = df.rename(columns={
            '日期': 'date',
            '开盘': 'open',
            '收盘': 'close',
            '最高': 'high',
            '最低': 'low',
            '成交量': 'volume',
            '成交额': 'amount',
            '振幅': 'amplitude',
            '涨跌幅': 'pct_chg',
            '涨跌额': 'change',
            '换手率': 'turn'
        })
        
        # 转换日期
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)
        
        return df
        
    except Exception as e:
        return None


def calculate_indicators(df):
    """计算技术指标"""
    df = df.copy()
    
    # 均线
    df['ma5'] = df['close'].rolling(5).mean()
    df['ma10'] = df['close'].rolling(10).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    
    # 20日最高价
    df['high_20'] = df['close'].rolling(20).max()
    
    # 突破因子（收盘价/20日最高价）
    df['breakout_20'] = df['close'] / df['high_20']
    
    # 距离20日高点的天数
    df['days_since_high'] = df.groupby((df['high_20'] != df['high_20'].shift(1)).cumsum()).cumcount(ascending=False)
    
    # 回调幅度
    df['pullback_pct'] = (df['high_20'] - df['close']) / df['high_20']
    
    # 成交量均线
    df['vol_ma5'] = df['volume'].rolling(5).mean()
    df['vol_ma20'] = df['volume'].rolling(20).mean()
    
    # 缩量程度（相对于20日高点时的成交量）
    df['vol_at_high'] = df['volume'].shift(df['days_since_high'].astype(int))
    df['vol_decrease'] = (df['vol_at_high'] - df['volume']) / df['vol_at_high']
    
    # MACD
    df['ema12'] = df['close'].ewm(span=12, adjust=False).mean()
    df['ema26'] = df['close'].ewm(span=26, adjust=False).mean()
    df['dif'] = df['ema12'] - df['ema26']
    df['dea'] = df['dif'].ewm(span=9, adjust=False).mean()
    df['macd'] = (df['dif'] - df['dea']) * 2
    
    # 振幅（百分比转小数）
    df['amplitude'] = df['amplitude'] / 100
    
    # 换手率（百分比转小数）
    df['turn'] = df['turn'] / 100
    
    # 量比
    df['vol_ratio'] = df['volume'] / df['vol_ma5']
    
    # 回踩均线距离
    df['ma5_dist'] = abs(df['close'] - df['ma5']) / df['close']
    df['ma10_dist'] = abs(df['close'] - df['ma10']) / df['close']
    
    return df


def calculate_score(row):
    """计算选股评分（100分制）"""
    score = 0
    
    # 1. 前期强势度（25分）：越接近20日新高得分越高
    breakout = row['breakout_20']
    if breakout >= 0.95:
        score += 25
    elif breakout >= 0.92:
        score += 22
    elif breakout >= 0.90:
        score += 20
    elif breakout >= 0.88:
        score += 17
    else:
        score += 15
    
    # 2. 回调幅度（15分）：7%-8%最佳
    pullback = row['pullback_pct']
    if 0.07 <= pullback <= 0.08:
        score += 15
    elif 0.06 <= pullback <= 0.09:
        score += 12
    else:
        score += 8
    
    # 3. 缩量程度（25分）：缩量越多得分越高
    vol_dec = row['vol_decrease']
    if pd.isna(vol_dec):
        vol_dec = 0
    
    if vol_dec >= 0.4:
        score += 25
    elif vol_dec >= 0.3:
        score += 22
    elif vol_dec >= 0.2:
        score += 18
    elif vol_dec >= 0.1:
        score += 15
    else:
        score += 10
    
    # 4. 回踩均线（15分）：回踩MA5越近得分越高
    ma5_dist = row['ma5_dist']
    if pd.isna(ma5_dist):
        ma5_dist = 0.1
    
    if ma5_dist <= 0.01:
        score += 15
    elif ma5_dist <= 0.02:
        score += 12
    elif ma5_dist <= 0.03:
        score += 10
    else:
        score += 8
    
    # 5. MACD位置（10分）：0轴上方得分高
    dif = row['dif']
    if pd.isna(dif):
        dif = 0
    
    if dif > 0:
        score += 10
    else:
        score += 5
    
    # 6. 企稳信号（10分）：当天收阳且放量得分高
    pct_chg = row['pct_chg'] / 100 if abs(row['pct_chg']) > 1 else row['pct_chg']
    vol_ratio = row['vol_ratio']
    if pd.isna(vol_ratio):
        vol_ratio = 1
    
    if pct_chg >= 0 and vol_ratio >= 1.0:
        score += 10
    elif pct_chg >= 0:
        score += 7
    else:
        score += 3
    
    return score


def find_today_signals(stock_list, target_date=None, min_score=70):
    """找出目标日期的选股信号"""
    
    if target_date is None:
        target_date = pd.Timestamp.now().strftime('%Y-%m-%d')
    
    print(f'\n正在计算选股信号（目标日期：{target_date}）...')
    
    all_signals = []
    count = 0
    
    for stock in stock_list:
        code = stock['code']
        count += 1
        
        if count % 100 == 0:
            print(f'  已处理 {count} 只，找到 {len(all_signals)} 个信号')
        
        # 获取股票数据
        df = get_stock_data(code)
        if df is None or len(df) < 30:
            continue
        
        # 计算指标
        df = calculate_indicators(df)
        
        # 找到目标日期的数据
        target_df = df[df['date'] == target_date]
        if len(target_df) == 0:
            continue
        
        row = target_df.iloc[0]
        
        # 跳过缺失值
        if pd.isna(row['ma20']) or pd.isna(row['breakout_20']) or pd.isna(row['pullback_pct']):
            continue
        
        # 基本条件
        # 1. 收盘价在MA20上方
        if row['close'] <= row['ma20']:
            continue
        
        # 2. 接近20日新高（突破因子 >= 0.85）
        if row['breakout_20'] < 0.85:
            continue
        
        # 3. 回调幅度6%-9%
        if row['pullback_pct'] < 0.06 or row['pullback_pct'] > 0.09:
            continue
        
        # 4. 回调2-6天
        if row['days_since_high'] < 2 or row['days_since_high'] > 6:
            continue
        
        # 5. 回调期间缩量（缩量10%以上）
        if pd.isna(row['vol_decrease']) or row['vol_decrease'] < 0.1:
            continue
        
        # 6. 当天必须收阳
        pct_chg = row['pct_chg'] / 100 if abs(row['pct_chg']) > 1 else row['pct_chg']
        if pct_chg < 0:
            continue
        
        # 7. 换手率2%-15%
        turn = row['turn']
        if turn < 0.02 or turn > 0.15:
            continue
        
        # 8. 振幅不超过8%
        if row['amplitude'] > 0.08:
            continue
        
        # 9. 均线多头排列
        if not (row['ma5'] > row['ma10'] > row['ma20']):
            continue
        
        # 计算评分
        score = calculate_score(row)
        
        if score >= min_score:
            signal = {
                'code': code,
                'name': stock['name'],
                'date': target_date,
                'close': row['close'],
                'score': score,
                'breakout_20': row['breakout_20'],
                'pullback_pct': row['pullback_pct'],
                'vol_decrease': row['vol_decrease'],
                'days_since_high': row['days_since_high'],
                'turn': turn,
                'amplitude': row['amplitude']
            }
            all_signals.append(signal)
    
    if len(all_signals) == 0:
        print('没有找到符合条件的股票')
        return None
    
    # 按评分排序
    signals_df = pd.DataFrame(all_signals)
    signals_df = signals_df.sort_values('score', ascending=False).reset_index(drop=True)
    
    print(f'\n选股完成！共找到 {len(signals_df)} 个符合条件的信号')
    
    return signals_df


def calculate_market_index(stock_list, target_date):
    """计算等权大盘指数，判断大盘择时"""
    print('\n正在计算大盘择时...')
    
    # 简化版：用沪深300指数代替等权指数
    try:
        df = ak.stock_zh_index_daily(symbol="sh000300")  # 沪深300
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)
        
        # 计算MA20
        df['ma20'] = df['close'].rolling(20).mean()
        
        # 找到目标日期前一个交易日
        target = pd.to_datetime(target_date)
        past_df = df[df['date'] < target]
        
        if len(past_df) == 0:
            return False
        
        last_row = past_df.iloc[-1]
        
        if pd.isna(last_row['ma20']):
            return False
        
        market_ok = last_row['close'] > last_row['ma20']
        
        print(f'  沪深300：{last_row["close"]:.2f}，MA20：{last_row["ma20"]:.2f}')
        print(f'  大盘择时：{"做多" if market_ok else "观望"}')
        
        return market_ok
        
    except Exception as e:
        print(f'  大盘择时计算失败：{e}，默认做多')
        return True


def main():
    print('=' * 60)
    print('V5.7 双因子策略 - 云端版每日选股')
    print('=' * 60)
    
    # 目标日期
    target_date = None
    if len(sys.argv) > 1:
        target_date = sys.argv[1]
    
    if target_date is None:
        target_date = pd.Timestamp.now().strftime('%Y-%m-%d')
    
    print(f'\n目标日期：{target_date}')
    print()
    
    # 获取股票列表
    stock_list = get_stock_list()
    
    # 大盘择时
    market_ok = calculate_market_index(stock_list, target_date)
    
    if not market_ok:
        print('\n大盘不好，今天空仓观望！')
        # 输出结果到文件（供推送脚本读取）
        result = {
            'date': target_date,
            'market_ok': False,
            'signal': None,
            'message': '大盘不好，今天空仓观望！'
        }
        with open('result.json', 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        return
    
    # 找出今天的选股信号
    signals_df = find_today_signals(stock_list, target_date=target_date, min_score=70)
    
    if signals_df is None or len(signals_df) == 0:
        print('\n今天没有符合条件的股票，空仓观望！')
        result = {
            'date': target_date,
            'market_ok': True,
            'signal': None,
            'message': '今天没有符合条件的股票，空仓观望！'
        }
        with open('result.json', 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        return
    
    # 选评分最高的那只
    best_stock = signals_df.iloc[0]
    
    # 计算买入价、止损价、止盈价
    buy_price = best_stock['close']
    stop_loss_price = buy_price * (1 - 0.025)  # 止损2.5%
    take_profit_price = buy_price * (1 + 0.30)  # 止盈30%
    
    # 输出结果
    print('\n' + '=' * 60)
    print('今日操盘明细')
    print('=' * 60)
    print()
    print(f'股票代码：{best_stock["code"]}')
    print(f'股票名称：{best_stock["name"]}')
    print(f'选股评分：{best_stock["score"]} 分')
    print(f'昨日收盘价：{best_stock["close"]:.2f} 元')
    print()
    print(f'买入策略：今日开盘价买入（高开>2%不买）')
    print(f'止损价：{stop_loss_price:.2f} 元（-2.5%）')
    print(f'止盈价：{take_profit_price:.2f} 元（+30%）')
    print(f'持股天数：6个交易日')
    print(f'移动止盈：盈利>5%后保本（止损上移到成本价）')
    print()
    print(f'突破因子：{best_stock["breakout_20"]:.2%}（接近20日新高）')
    print(f'回调幅度：{best_stock["pullback_pct"]:.2%}')
    print(f'回调天数：{best_stock["days_since_high"]} 天')
    print(f'缩量程度：{best_stock["vol_decrease"]:.2%}')
    print(f'换手率：{best_stock["turn"]:.2%}')
    print(f'振幅：{best_stock["amplitude"]:.2%}')
    print()
    
    # 备选股票
    if len(signals_df) > 1:
        print('备选股票（评分前5）：')
        for i in range(min(5, len(signals_df))):
            row = signals_df.iloc[i]
            print(f'  {i+1}. {row["code"]} {row["name"]} - {row["score"]}分 - {row["close"]:.2f}元')
        print()
    
    print('=' * 60)
    print('操盘纪律：')
    print('  1. 严格按开盘价买入，高开>2%放弃')
    print('  2. 严格止损，到止损价立刻卖')
    print('  3. 到止盈价立刻卖，不贪')
    print('  4. 持股6天，到时间就卖')
    print('  5. 大盘不好就空仓，不硬做')
    print('=' * 60)
    
    # 保存结果到JSON（供推送脚本使用）
    result = {
        'date': target_date,
        'market_ok': True,
        'signal': {
            'code': best_stock['code'],
            'name': best_stock['name'],
            'score': int(best_stock['score']),
            'close': float(best_stock['close']),
            'stop_loss': float(stop_loss_price),
            'take_profit': float(take_profit_price),
            'hold_days': 6,
            'breakout_20': float(best_stock['breakout_20']),
            'pullback_pct': float(best_stock['pullback_pct']),
            'vol_decrease': float(best_stock['vol_decrease']),
            'days_since_high': int(best_stock['days_since_high']),
            'turn': float(best_stock['turn']),
            'amplitude': float(best_stock['amplitude'])
        },
        'alternatives': []
    }
    
    # 备选股票
    if len(signals_df) > 1:
        for i in range(min(5, len(signals_df))):
            row = signals_df.iloc[i]
            result['alternatives'].append({
                'code': row['code'],
                'name': row['name'],
                'score': int(row['score']),
                'close': float(row['close'])
            })
    
    with open('result.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print('\n结果已保存到 result.json')


if __name__ == '__main__':
    main()
