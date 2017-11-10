import statistics
import math
import numpy
import ContractDef.contract_info as ci
import FileUtil.file_parser as fp
import Plots.plots as plots
import matplotlib.pyplot as plt
import DateDef.date_util as du

def StatArbStrategy(contracts, data_csv=[], data_list=[], **strategy_params):
  """
  Trade contract[0] using contract[1] as leading indicator

  Trading parameters:
  net_change:         how much does today's price have to deviate from
                      ma to consider trend to be starting
  ma_lookback_days:   how many days to build moving average over
  loss_ticks:         where to stop out on a losing position

  :param data_csv: csv filename to load data from
  :param data_list: list to load data from
  :param strategy_params: dictionary of trading parameters
  :return: (error/success code, list of trade information)
  """
  trades = []
  log_level = strategy_params.pop('log_level', 0)

  if not data_csv and not data_list:
    if log_level > 0:
      print('ERROR neither have datafile nor datalist')
    return -1, None, None

  if data_csv and data_list:
    if log_level > 0:
      print('ERROR cant have both datafile and datalist')
    return -1, None, None

  # get an iterable based on arguments passed
  market_data_1 = data_list or open(data_csv[0], 'r')
  market_data_2 = data_list or open (data_csv[1], 'r')
  if log_level > 0:
    print('INFO opened data file/list ', market_data_1, ' and ', market_data_2)

  # dump out trading parameters
  if log_level > 0:
    print('INFO trading params ', strategy_params)

  # pull out parameters, use defaults if missing
  ma_lookback_days = int(strategy_params.pop('ma_lookback_days', 10))
  o_loss_ticks = float(strategy_params.pop('loss_ticks', 5.0))
  o_net_change = float(strategy_params.pop('net_change', 5.0))
  risk_dollars = float(strategy_params.pop('risk_dollars', 1000.0))
  min_correlation = float(strategy_params.pop('min_correlation', 0.75))

  # define some model specific variables
  lookback_prices = [[], []] # maintain, update ma
  lookback_dev_from_ma = [[], []]
  lookback_dev_from_projection = []
  my_position, my_vwap, my_pnl = 0, 0, 0 # position, position vwap, pnl

  market_data = [list(reversed(list(market_data_1))), list(reversed(list(market_data_2)))]
  market_data_index = [0, 0]

  while market_data_index[0] < len(market_data[0]) and market_data_index[1] < len(market_data[1]):
    date, open_price, high_price, low_price, close_price = [0, 0], [0, 0], [0, 0], [0, 0], [0, 0]
    try:
      if log_level > 0:
        print('INFO looking at index: ', market_data_index[0], '/', len(market_data[0]),
              ' ', market_data_index[1], '/', len(market_data[1]))

      # unpack list
      for index in [0, 1]:
        date[index], open_price[index], high_price[index], low_price[index], close_price[index] =\
          fp.TokenizeToPriceInfo(contracts[index], market_data[index][market_data_index[index]])
    except ValueError or TypeError:
      # need to update indices or you'll get stuck in an infinite loop
      for index in [0, 1]:
        market_data_index[index] += 1
      continue

    # sanity check to make sure we are looking at same day on both contracts
    if date[0] != date[1]:
      # need to figure out which contract is lagging and bring that upto speed
      if du.CompareDates(date[0], date[1]) < 0:
        market_data_index[0] += 1
      else:
        market_data_index[1] += 1
      continue

    for index in [0, 1]:
      market_data_index[index] += 1
      lookback_prices[index].append([high_price[index], low_price[index], close_price[index]])

    if len(lookback_prices[0]) < ma_lookback_days + 1:
      # not initialized yet, push and continue
      if log_level > 0:
        print('not enough lookback_prices history', lookback_prices, ma_lookback_days, sep=' ')
      continue

    # save ma and update list
    # print(list(row[2] for row in lookback_prices))
    ma, vol, dev_from_ma = [0, 0], [0, 0], [0, 0]
    for index in [0, 1]:
      ma[index] = statistics.mean(row[2] for row in lookback_prices[index])
      vol[index] = statistics.mean(abs(row[0] - row[1]) for row in lookback_prices[index])
      dev_from_ma[index] = close_price[index] - ma[index]
      lookback_dev_from_ma[index].append(dev_from_ma[index])

    # Need at least 2 points, not enough degrees of freedom
    if len(lookback_dev_from_ma[0]) < 2:
      continue

    corr = numpy.corrcoef(lookback_dev_from_ma[0], lookback_dev_from_ma[1])
    cov = numpy.cov(lookback_dev_from_ma[0], lookback_dev_from_ma[1])
    corr_0_1 = corr[0, 1] # get the correlation between the 2 series

    # get the strength of the moves
    # this holds the answer to 'for every 1 unit move in B, how much should A move'
    # we will use this to predict expected moves and then use the difference
    # with actual move to accumulate positions
    cov_0_1 = cov[0, 0] / cov[0, 1]

    # project what the price-change should be
    # this is designed so that for weaker correlations, projections are dampened
    projected_dev_from_ma = dev_from_ma[1] * cov_0_1
    projected_price = ma[0] + projected_dev_from_ma
    dev_from_projection = projected_dev_from_ma * abs(corr_0_1) - dev_from_ma[0]
    if math.isnan(dev_from_projection) or corr_0_1 < min_correlation:
      if log_level > 0:
        print('Skipping because dev_from_projection:', dev_from_projection, 'or correlation:', corr_0_1, 'less than', min_correlation)
      continue

    # track it so we know how big an average deviation is
    lookback_dev_from_projection.append(dev_from_projection)  # this measure only cares about the magnitude
    dev_from_projection_vol = statistics.mean(abs(item) for item in lookback_dev_from_projection)

    if log_level > 0:
      print('dev_from_projection', dev_from_projection, 'dev_from_projection_vol', dev_from_projection_vol, 'entries', lookback_dev_from_projection, sep=' ')

    if len(lookback_dev_from_ma[0]) < ma_lookback_days + 1:
      # need to have a long enough history
      # of relative deviations to project in the future
      if log_level > 0:
        print('not enough lookback_dev_from_ma history', len(lookback_dev_from_ma[0]), ma_lookback_days, sep=' ')
      continue

    for index in [0, 1]:
      while len(lookback_prices[index]) > ma_lookback_days:
        lookback_prices[index].pop(0)
      while len(lookback_dev_from_ma[index]) > ma_lookback_days:
        lookback_dev_from_ma[index].pop(0)
    while len(lookback_dev_from_projection) > ma_lookback_days:
      lookback_dev_from_projection.pop(0)

    if log_level > 0:
      print(contracts[0].Name, 'projected by', contracts[1].Name, 'correlation:', corr_0_1, 'coefficient:', cov_0_1)
      print('projected_dev_from_ma', projected_dev_from_ma, 'actual', dev_from_ma[0], 'dev_from_projection', dev_from_projection, sep=' ')

    loss_ticks = o_loss_ticks * vol[0]
    net_change = o_net_change * dev_from_projection_vol

    if log_level > 0:
      print('INFO vol:', vol, 'adjusted params:', 'net_change:', net_change, 'loss_ticks:', loss_ticks,
            sep=' ')

    traded_today = False

    if my_position == 0: # flat, see if we want to get into a position
      # how much did today's close price deviate from moving average ?
      # +ve value means breaking out to the upside
      # -ve value means breaking out to the downside
      if abs(dev_from_projection) > net_change: # blown out
        trade_size = int((risk_dollars / contracts[0].TickValue) / loss_ticks + 1)
        my_position = trade_size * (1 if dev_from_projection > 0 else -1)
        my_vwap = close_price[0]
        trades.append([date[0],('B' if dev_from_projection > 0 else 'S'), trade_size, close_price[0], my_position, my_pnl, dev_from_projection_vol, ma[0], dev_from_projection, projected_price, corr_0_1])
        traded_today = True

        if log_level > 0:
          print('INFO initiating position ', trades[-1])
    else: # have a position already, check for stop outs
      if ((my_position > 0 and my_vwap - low_price[0] > loss_ticks) or
          (my_position < 0 and high_price[0] - my_vwap > loss_ticks)):
        stopout_price = my_vwap +\
                        (loss_ticks * (1 if my_position < 0 else -1))
        trade_pnl = abs(my_position) * loss_ticks * contracts[0].TickValue
        my_pnl -= trade_pnl
        buysell = ('S' if my_position > 0 else 'B')

        trades.append([date[0], buysell, abs(my_position), stopout_price, 0, my_pnl, dev_from_projection_vol, ma[0], dev_from_projection, projected_price, corr_0_1])
        traded_today = True
        my_position = 0

        if log_level > 0:
          print('INFO stopped out ', trades[-1])
      elif abs(dev_from_projection) < 0.5 * net_change: # deviation dying out
        stopout_price = close_price[0]
        trade_pnl = my_position * (stopout_price - my_vwap) * contracts[0].TickValue
        my_pnl += trade_pnl
        buysell = ('S' if my_position > 0 else 'B')

        trades.append (
          [date[0], buysell, abs (my_position), stopout_price, 0, my_pnl, vol[0], ma[0], dev_from_projection_vol, projected_price, corr_0_1])
        traded_today = True
        my_position = 0

        if log_level > 0:
          print('INFO took a win ', trades[-1])

    if not traded_today:
      unreal_pnl = my_position * (close_price[0] - my_vwap) * contracts[0].TickValue
      trades.append([date[0], '-', my_position, close_price[0], 0, my_pnl + unreal_pnl, dev_from_projection_vol, ma[0], dev_from_projection, projected_price, corr_0_1])

  return 0, trades
