import os
import sys
import glob
import json
import numpy as np
import pandas as pd
import quantstats as qs

from InquirerPy import prompt
from pathlib import Path
from freqtrade.configuration import TimeRange
from freqtrade.data.history import load_data

qs.extend_pandas()

def prompt_backtest_results(backtest_dir: str = './user_data/backtest_results', using_latest: bool = False) -> str:
    backtest_results_path = f'{backtest_dir}/backtest-result-*.json'
    backtest_result_files = map(os.path.basename, sorted(glob.glob(backtest_results_path),
                                                            key=os.path.getmtime, reverse=True))
    backtest_result_options = list(backtest_result_files)

    if len(backtest_result_options) == 0:
        print(f'No backtest results found in {backtest_dir}')
        sys.exit(1)

    if using_latest is True:
        return backtest_result_options[0]

    questions = [{
        'type': 'list',
        'name': 'backtest_result_file',
        'message': 'Please select the BackTest results you want to use: ',
        'choices': backtest_result_options
    }]

    answers = prompt(questions=questions)
    return answers.get('backtest_result_file')


user_data_dir = './user_data'
dataformat_ohlcv = 'json'
backtest_dir = f'{user_data_dir}/backtest_results'
backtest_file = prompt_backtest_results(backtest_dir)
backtest_time = backtest_file.replace('backtest-result-', '').replace('.json', '')
backtest_file_path = f'{backtest_dir}/{backtest_file}'
file_object = open(backtest_file_path, 'r')
backtest_results = json.load(file_object)

for strategy in backtest_results['strategy'].keys():
  strategy_results = backtest_results['strategy'][strategy]
  starting_balance = strategy_results['starting_balance']
  # backtest_timeframe = strategy_results['timeframe']
  backtest_timeframe = '1d'
  backtest_timerange = TimeRange.parse_timerange(strategy_results['timerange'])
  backtest_pairs = strategy_results['pairlist']
  backtest_trades = pd.DataFrame(strategy_results['trades'])
  if len(backtest_trades) <= 0:
    print(f'Strategy {strategy} has no trades')
    continue

  backtest_trades['open_date'] = pd.to_datetime(backtest_trades['open_date'], utc=True, infer_datetime_format=True)
  daily_returns = backtest_trades[['open_date', 'profit_abs']].groupby(pd.Grouper(key="open_date", freq='D')).sum('profit_abs')
  daily_returns['balance'] = np.cumsum(daily_returns['profit_abs']) + starting_balance

  df_candle = load_data(
      datadir=Path(user_data_dir, 'data', 'binance'),
      pairs=backtest_pairs,
      timeframe=backtest_timeframe,
      timerange=backtest_timerange,
      data_format=dataformat_ohlcv,
  )

  df_benchmark = pd.concat([df_candle[pair].set_index('date')
              .rename({'close': pair}, axis=1)[pair] for pair in df_candle], axis=1)

  df_benchmark['mean'] = df_benchmark.mean(axis=1)
  df_benchmark['sum'] = df_benchmark.sum(axis=1)
  df_benchmark.index = pd.to_datetime(df_benchmark.index, utc=True, infer_datetime_format=True)

  benchmark_type = 'mean'
  benchmark_dates = pd.date_range(df_benchmark.index[0], df_benchmark.index[-1], freq='D').tz_localize(None)
  df_benchmark = pd.Series(df_benchmark[benchmark_type]).pct_change(1).values
  benchmark_time_series = pd.Series(df_benchmark, index=pd.to_datetime(list(benchmark_dates)))

  return_dates = pd.date_range(daily_returns.index[0], daily_returns.index[-1], freq='D').tz_localize(None)
  daily_returns = pd.Series(daily_returns['balance']).pct_change(1).values
  returns_time_series = pd.Series(daily_returns, index=pd.to_datetime(list(return_dates))).fillna(0)

  output_file_path = f'{user_data_dir}/plot/PlotBenchmarkReports-{strategy}-{backtest_time}.html'
  qs.reports.html(returns=returns_time_series, benchmark=benchmark_time_series, title=f'{strategy} {backtest_time}', output=output_file_path)
  print(f'Ploted benchmark report for strategy {strategy} to {output_file_path}')
