import sys, getopt, statistics
import Strategies.ContractDef.contract_info as ci
import Strategies.FileUtil.file_parser as fp
import Strategies.DateDef.date_util as dt
import Strategies.Plots.plots as plt

from trader import *
from portfolio_manager import *

SHORTCODE_DESCRIPTION = {
  'ES':'S&P Equity index',
  'NQ':'NASDAQ Equity Index',
  'CL':'Crude Oil',
  'HO':'Heating Oil',
  '6E':'Euro USD',
  '6B':'British Pound USD',
  'ZN':'US 10 year treasury',
  'ZB':'US 30 year treasury',
  'GC':'Gold',
  'SI':'Silver',
  'ZC':'Corn',
  'ZW':'Wheat'
}
indep_shortcode_list = ['ES', 'NQ',  # s&p, nasdaq
                        'CL', 'HO',  # crude, heating
                        '6E', '6B',  # euro, gbp
                        'ZN', 'ZB',  # 10yr, 30yr
                        'GC', 'SI',  # gold, silver
                        'ZC', 'ZW']  # corn, wheat
shortcode_pairs = [['ES', 'NQ'],  # s&p, nasdaq
                   ['CL', 'HO'],  # crude, heating
                   ['6E', '6B'],  # euro, gbp
                   ['ZN', 'ZB'],  # 10yr, 30yr
                   ['GC', 'SI'],  # gold, silver
                   ['ZC', 'ZW']]  # corn, wheat
shortcode_relative = [
  ['ES', 'NQ'],  # s&p using nasdaq
  ['NQ', 'ES'],  # nasdaq using s&p

  ['CL', 'HO'],  # crude using heating
  ['HO', 'CL'],  # heating using crude

  ['6E', '6B'],  # euro using gbp
  ['6B', '6E'],  # gbp using euro

  ['ZN', 'ZB'],  # 10yr using 30yr
  ['ZB', 'ZN'],  # 30yr using 10yr

  ['GC', 'SI'],  # gold using silver
  ['SI', 'GC'],  # silver using gold

  ['ZC', 'ZW'],  # corn using wheat
  ['ZW', 'ZC']  # wheat using corn
]

portfolio_managers_list = [UniformAllocPM, IndividualPnlAllocPM, IndividualSharpeAllocPM, MarkowitzAllocPM]
# portfolio_managers_list = [UniformAllocPM, RegimePredictiveAllocPM]
trader_list = [TrendFollowTrader, MeanReversionTrader, RelativeValueTrader, PairsTrader]

# create an instance of every portfolio manager style known to us
# for each one of those instances, add every possible trader x contract pairs
# return a list of all the instances created
def InitializePMs():
  pm_list, regime_pm = [], []
  contracts = {TrendFollowTrader: indep_shortcode_list,
               MeanReversionTrader: indep_shortcode_list,
               RelativeValueTrader: shortcode_relative,
               PairsTrader: shortcode_pairs}
  tfd = {'log_level': 0, 'loss_ticks': 0.1, 'net_change': 0.25}
  mrd = {'log_level': 0, 'loss_ticks': 0.2, 'net_change': 0.75}
  ptd = {'log_level': 0, 'loss_ticks': 0.2, 'net_change': 0.75}
  rvd = {'log_level': 0, 'loss_ticks': 0.2, 'net_change': 0.75, 'min_correlation': 0.65}
  strategy_params = {TrendFollowTrader: tfd, MeanReversionTrader: mrd, RelativeValueTrader: rvd, PairsTrader: ptd}

  for pm_type in portfolio_managers_list:
    pm = pm_type()
    if pm.style == AllocationStyle.RegimePredictiveAlloc:
      regime_pm.append(pm)
    else:
      pm_list.append(pm)
    # print('\n' + '>' * 5 + ' ' + str(pm))

    for trader_type in trader_list:
      strategy_param = strategy_params[trader_type]

      for contract in contracts[trader_type]:
        trader = trader_type(contract, strategy_param)
        pm.AddTrader(trader)
        # print('>' * 10 + ' ' + str(trader))

    # print('>' * 5 + ' Finished with ' + str(pm))

  return pm_list, regime_pm

# open every market data file and read contents in chrono order
# maintain indices to last line in each list, start at 0
# fudge list of data for every contract so every list has exactly the
def LoadMarketDataLines(shc_market_data_lines, shc_market_line_index):
  for shc in indep_shortcode_list:
    filename = 'MarketData/csvs/market_data_' + shc + '.csv'
    shc_market_data_lines[shc] = list(reversed(list(open(filename, 'r'))))
    shc_market_line_index[shc] = 0

    print('Loaded:' + shc + ' from:' + filename + ' lines:' + str(len(shc_market_data_lines[shc])))

# check last indexed row of each contract and find out which is the oldest update
def FindOldestDate(shc_market_data_lines, shc_market_line_index):
  last_date = None
  for shc in shc_market_data_lines.keys():
    contract = ci.ContractInfoDatabase[shc]
    line = shc_market_data_lines[shc][shc_market_line_index[shc]]
    date = fp.TokenizeToDate(contract, line)
    if (not last_date) or (dt.CompareDates(date, last_date) < 0):
      last_date = date

  return last_date

# start from oldest date first,
# then play back each update in chronological order
# from list for every contract.
# for every update portfolio manager with the market update
def ReplayMarketData(shc_market_data_lines, shc_market_line_index, pm_list):
  print('Running sims for ' + str(pm_list))

  # oldest date
  last_date = FindOldestDate(shc_market_data_lines, shc_market_line_index)
  line_num = 0

  while True:
    if not last_date:
      break

    next_line = None
    next_shc = None
    next_date = last_date

    for shc in shc_market_data_lines.keys():
      if shc_market_line_index[shc] >= len(shc_market_data_lines[shc]) - 1: # -1 because of header in input
        # print('reached end of stream for ' + shc + ' skipping.')
        continue

      contract = ci.ContractInfoDatabase[shc]
      line = shc_market_data_lines[shc][shc_market_line_index[shc]]
      date = fp.TokenizeToDate(contract, line)
      # print('comparing ' + shc + ' date:' + date + ' & next_date:' + next_date)

      if dt.CompareDates(next_date, date) >= 0:
        next_line, next_shc, last_date, next_date = line, shc, date, date
        shc_market_line_index[shc] = shc_market_line_index[shc] + 1
        break

    if not next_shc:
      last_date = FindOldestDate(shc_market_data_lines, shc_market_line_index)
      continue

    for pm in pm_list:
      pm.OnMarketDataUpdate(next_shc, next_date, next_line)

    # print('next_line: ' + next_line.strip() + ' next_shc: ' + next_shc + ' last_date: ' + last_date)
    # print(shc_market_line_index)

  for shc in shc_market_data_lines.keys():
    shc_market_line_index[shc] = 0

if __name__ == '__main__':
  print('\nInitializing Portfolio Managers...')
  # a list of our portfolio manager competing against each other
  pm_list, regime_pm = InitializePMs()
  for pm in pm_list:
    print(pm)
  for pm in regime_pm:
    print(pm)

  print('\nLoading up market data files...')
  # open every market data file and read data
  shc_market_data_lines = {} # this is a map from contract name to market data lines
  shc_market_line_index = {} # this is a map from contract name to last read index
  LoadMarketDataLines(shc_market_data_lines, shc_market_line_index)

  print('\nPlaying data and running sims...')
  ReplayMarketData(shc_market_data_lines, shc_market_line_index, pm_list)
  print(end='\n')
  for pm in pm_list:
    if pm.style == AllocationStyle.UniformAlloc:
      regime_pm[0].SetUniformReturns(pm.traders)
      break
  ReplayMarketData(shc_market_data_lines, shc_market_line_index, regime_pm)
  pm_list.append(regime_pm[0])
  print(end='\n')

  print('\nSummarizing portfolio manager stats...')
  # summarize one pm at a time, that will summarize strats under management one at a time
  all_dates, pm_pnl_list, std_mean = [], {}, []
  for pm in pm_list:
    pm.SummarizePerformance()
    if len(all_dates) <= 0:
      all_dates = pm.all_dates

    std_mean.append([pm.stdev_pnl, pm.avg_pnl, str(pm)])

    pm_pnl_list[str(pm)] = pm.pnl_list

  print('\nComparing portfolio managers...')
  plt.ComparePlots(all_dates, pm_pnl_list)
  plt.PlotEfficientFrontierPlot(std_mean)
