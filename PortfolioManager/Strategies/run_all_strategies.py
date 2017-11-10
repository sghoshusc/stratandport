import sys, getopt, statistics
import ContractDef.contract_info as ci
import Plots.plots as plots
import matplotlib.pyplot as plt

import trend_following as tfs
import mean_reversion as mrs
import pairs_reversion as prs
import stat_arb as sas

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

indep_shortcode_list = ['ES', 'NQ', # s&p, nasdaq
                        'CL', 'HO', # crude, heating
                        '6E', '6B', # euro, gbp
                        'ZN', 'ZB', # 10yr, 30yr
                        'GC', 'SI', # gold, silver
                        'ZC', 'ZW'] # corn, wheat

shortcode_pairs = [['ES', 'NQ'], # s&p, nasdaq
                   ['CL', 'HO'], # crude, heating
                   ['6E', '6B'], # euro, gbp
                   ['ZN', 'ZB'], # 10yr, 30yr
                   ['GC', 'SI'], # gold, silver
                   ['ZC', 'ZW']] # corn, wheat

shortcode_relative = [
                  ['ES', 'NQ'], # s&p using nasdaq
                  ['NQ', 'ES'], # nasdaq using s&p

                  ['CL', 'HO'], # crude using heating
                  ['HO', 'CL'], # heating using crude

                  ['6E', '6B'], # euro using gbp
                  ['6B', '6E'], # gbp using euro

                  ['ZN', 'ZB'], # 10yr using 30yr
                  ['ZB', 'ZN'], # 30yr using 10yr

                  ['GC', 'SI'], # gold using silver
                  ['SI', 'GC'], # silver using gold

                  ['ZC', 'ZW'], # corn using wheat
                  ['ZW', 'ZC'] # wheat using corn
                  ]
def main(args):
  print('========== CME Futures Contract descriptions ==========')
  for shc in indep_shortcode_list:
    print('\t', shc, '=>', SHORTCODE_DESCRIPTION[shc], end='')
    ci.ContractInfoDatabase[shc].ToString()

  shortcode_results = {}
  print('\nRunning TrendFollowing strategy, close plot window to proceed to next contract. Ctrl-C to quit.')
  for shortcode in indep_shortcode_list:
    print('\tRunning TrendFollowing on', shortcode, SHORTCODE_DESCRIPTION[shortcode])

    filename = 'MarketData/csvs/market_data_' + shortcode + '.csv'
    ret_code, trades = tfs.TrendFollowStrategy(
      ci.ContractInfoDatabase[shortcode],
      data_csv=filename,
      data_list=[],
      net_change=0.25, # trend starting, so need to get in early
      ma_lookback_days=40,
      loss_ticks=0.1, # losses will be smaller but frequent
      risk_dollars=1000,
      log_level=0)

    if ret_code == 0:
      shortcode_results[shortcode] = list(trades)
      plots.PlotTrades('TrendFollowing', trades, ci.ContractInfoDatabase[shortcode], 0, len(trades))

  plots.MergeAndPlotTrades('TrendFollowing', shortcode_results, ci.ContractInfoDatabase)

  shortcode_results = {}
  print('\nRunning MeanReversion strategy, close plot window to proceed to next contract. Ctrl-C to quit.')
  for shortcode in indep_shortcode_list:
    print('\tRunning MeanReversion on', shortcode, SHORTCODE_DESCRIPTION[shortcode])

    filename = 'MarketData/csvs/market_data_' + shortcode + '.csv'
    ret_code, trades = mrs.MeanReversionStrategy(
      ci.ContractInfoDatabase[shortcode],
      data_csv=filename,
      data_list=[],
      net_change=0.75, # mean reversion, so bet till blown out significantly
      ma_lookback_days=40,
      loss_ticks=0.2, # losses will be bigger but infrequent
      risk_dollars=1000,
      log_level=0)

    if ret_code == 0:
      shortcode_results[shortcode] = list(trades)
      plots.PlotTrades('MeanReversion', trades, ci.ContractInfoDatabase[shortcode], 0, len(trades))

  plots.MergeAndPlotTrades('MeanReversion', shortcode_results, ci.ContractInfoDatabase)

  shortcode_results = {}
  print('\nRunning PairsTrading strategy, close plot window to proceed to next contract. Ctrl-C to quit.')
  for shortcode_1, shortcode_2 in shortcode_pairs:
    print('\tRunning PairsTrading on', shortcode_1, SHORTCODE_DESCRIPTION[shortcode_1], 'VS.', shortcode_2, SHORTCODE_DESCRIPTION[shortcode_2])

    filename_1 = 'MarketData/csvs/market_data_' + shortcode_1 + '.csv'
    filename_2 = 'MarketData/csvs/market_data_' + shortcode_2 + '.csv'
    ret_code, synthetic_contract, trades = prs.PairsReversionStrategy (
      [ci.ContractInfoDatabase [shortcode_1],
       ci.ContractInfoDatabase [shortcode_2]],
      data_csv=[filename_1, filename_2],
      data_list=[],
      net_change=0.75,  # mean reversion, so bet till blown out significantly
      ma_lookback_days=40,
      loss_ticks=0.2,  # losses will be bigger but infrequent
      risk_dollars=1000,
      log_level=0)

    if ret_code == 0:
      shortcode_results [synthetic_contract.Name] = list (trades)
      plots.PlotTrades ('PairsTrading', trades, synthetic_contract, 0, len (trades))

  plots.MergeAndPlotTrades ('PairsTrading', shortcode_results, ci.ContractInfoDatabase)

  shortcode_results = {}
  print('\nRunning StatArb strategy, close plot window to proceed to next contract. Ctrl-C to quit.')
  for shortcode_1, shortcode_2 in shortcode_relative:
    print('\tRunning StatArb on', shortcode_1, SHORTCODE_DESCRIPTION[shortcode_1], 'using', shortcode_2, SHORTCODE_DESCRIPTION[shortcode_2])

    filename_1 = 'MarketData/csvs/market_data_' + shortcode_1 + '.csv'
    filename_2 = 'MarketData/csvs/market_data_' + shortcode_2 + '.csv'
    ret_code, trades = sas.StatArbStrategy (
      [ci.ContractInfoDatabase [shortcode_1],
       ci.ContractInfoDatabase [shortcode_2]],
      data_csv=[filename_1, filename_2],
      data_list=[],
      net_change=0.75,  # mean reversion, so bet till blown out significantly
      ma_lookback_days=40,
      loss_ticks=0.2,  # losses will be bigger but infrequent
      risk_dollars=1000,
      min_correlation=0.65,
      log_level=0)

    if ret_code == 0:
      shortcode_results [shortcode_1] = list (trades)

      # I would like to see additional columns for this strategy
      contract = ci.ContractInfoDatabase [shortcode_1]
      contract.Name = shortcode_1 + ' using ' + shortcode_2
      plots.PlotStatArbTrades ('StatArb', trades, contract, 0, len (trades))

  plots.MergeAndPlotTrades ('StatArb', shortcode_results, ci.ContractInfoDatabase)

if __name__ == '__main__':
  main(sys.argv[1:])
