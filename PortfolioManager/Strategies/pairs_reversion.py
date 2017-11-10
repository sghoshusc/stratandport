import statistics
import ContractDef.contract_info as ci
import FileUtil.file_parser as fp
import Plots.plots as plots
import matplotlib.pyplot as plt
import DateDef.date_util as du

def ComputeSpreadPrice(ratio, is_inverted, price_1, price_2):
  # basic idea is to multiply the leg with lower dollar volatility
  # with a higher ratio to get the correct hedge size
  spread_price = price_1 - price_2 * ratio
  if is_inverted:
    spread_price = price_1 * ratio - price_2

  # print('INFO price_1, price_2, ratio, spread_price, is_inverted ', price_1, price_2, ratio, spread_price, is_inverted)
  return spread_price

def PairsReversionStrategy(contracts, data_csv=[], data_list=[], **strategy_params):
  """
  Run a mean reversion strategy on either the data_csv file
  or the data_list list, if both are passed, I will return error.

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

  # define some model specific variables
  lookback_prices = [[], [], []] # maintain, update ma
  my_position, my_vwap, my_pnl = [0, 0, 0], [0, 0, 0], [0, 0, 0] # position, position vwap, pnl

  market_data = [list(reversed(list(market_data_1))), list(reversed(list(market_data_2)))]
  market_data_index = [0, 0]

  syn_contract = ci.ContractInfo(contracts[0].Name + ' VS. ' + contracts[1].Name, 0.01, 10)

  while market_data_index[0] < len(market_data[0]) and market_data_index[1] < len(market_data[1]):
    date, open_price, high_price, low_price, close_price = [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]
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
      continue

    # save ma and update list
    # print(list(row[2] for row in lookback_prices))
    ma, vol, dollar_vol, weight = [0, 0, 0], [0, 0, 0], [0, 0, 0], [1, 1, 1]
    for index in [0, 1]:
      ma[index] = statistics.mean(row[2] for row in lookback_prices[index])
      vol[index] = statistics.mean(abs(row[0] - row[1]) for row in lookback_prices[index])
      dollar_vol[index] = vol[index] * contracts[index].TickValue

    is_inverted = False # maintain a flag if we invert ratio
    ratio = dollar_vol[0] / dollar_vol[1]
    if ratio < 1:
      ratio = 1 / ratio
      is_inverted = True

    high_price[2] = ComputeSpreadPrice(ratio, is_inverted, high_price[0], high_price[1])
    low_price[2] = ComputeSpreadPrice(ratio, is_inverted, low_price[0], low_price[1])
    close_price[2] = ComputeSpreadPrice(ratio, is_inverted, close_price[0], close_price[1])
    lookback_prices[2].append([high_price[2], low_price[2], close_price[2]])
    ma[2] = statistics.mean(row[2] for row in lookback_prices[2])
    vol[2] = statistics.mean(abs(row[0] - row[1]) for row in lookback_prices[2])
    dev_from_ma = close_price[2] - ma[2]

    if log_level > 0:
      print('INFO vol ', vol, ' dollar vol ', dollar_vol, ' ratio ', ratio)

    for index in [0, 1, 2]:
      if len(lookback_prices[index]) >= ma_lookback_days:
        lookback_prices[index].pop(0)

    loss_ticks = o_loss_ticks * vol[2]
    net_change = o_net_change * vol[2]

    # this is a tough one, and this solution is imperfect
    # but preferred for its simplicity
    spread_tick_value = min(contracts[0].TickValue, contracts[1].TickValue * ratio)
    if is_inverted:
      spread_tick_value = min(contracts[0].TickValue * ratio, contracts[1].TickValue)

    if log_level > 0:
      print('INFO vol:', vol, 'adjusted params:', 'net_change:', net_change, 'loss_ticks:', loss_ticks,
            'spread_tick_value:', spread_tick_value, sep=' ')

    traded_today = False

    if my_position[2] == 0: # flat, see if we want to get into a position
      # how much did today's close price deviate from moving average ?
      # +ve value means breaking out to the upside
      # -ve value means breaking out to the downside
      if abs(dev_from_ma) > net_change: # blown out
        trade_size = int((risk_dollars / spread_tick_value) / loss_ticks + 1)
        my_position[0] = trade_size * (ratio if is_inverted else 1)
        my_position[1] = trade_size * (1 if is_inverted else ratio)
        my_vwap = list(close_price)
        my_position[2] = trade_size * (1 if dev_from_ma < 0 else -1)
        my_vwap[2] = close_price[2]
        trades.append([date[0], ('B' if dev_from_ma < 0 else 'S'), trade_size, close_price[2],
                       my_position[2], my_pnl[2], vol[2], ma[2], dev_from_ma, high_price[2], low_price[2]])
        traded_today = True

        if log_level > 0:
          print('INFO initiating position ', trades[-1])
    else: # have a position already, check for stop outs
      if ((my_position[2] > 0 and my_vwap[2] - low_price[2] > loss_ticks) or
          (my_position[2] < 0 and high_price[2] - my_vwap[2] > loss_ticks)):
        stopout_price = my_vwap[2] +\
                        (loss_ticks * (1 if my_position[2] < 0 else -1))
        trade_pnl = abs(my_position[2]) * loss_ticks * spread_tick_value
        my_pnl[2] -= trade_pnl
        buysell = ('S' if my_position[2] > 0 else 'B')

        trades.append([date[0], buysell, abs(my_position[2]), stopout_price, 0, my_pnl[2], vol[2], ma[2], dev_from_ma, high_price[2], low_price[2]])
        traded_today = True
        my_position = [0, 0, 0]

        if log_level > 0:
          print('INFO stopped out ', trades[-1])
      elif abs(dev_from_ma) < 0.5 * net_change: # trend dying out
        my_pnl[0] += my_position[0] * (close_price[0] - my_vwap[0]) * contracts[0].TickValue
        my_pnl[1] += my_position[1] * (close_price[1] - my_vwap[1]) * contracts[1].TickValue
        my_pnl[2] = my_pnl[0] + my_pnl[1]
        buysell = ('S' if my_position[2] > 0 else 'B')

        trades.append (
          [date[0], buysell, abs(my_position[2]), close_price[2], 0, my_pnl[2], vol[2], ma[2], dev_from_ma, high_price[2], low_price[2]])
        traded_today = True
        my_position = [0, 0, 0]

        if log_level > 0:
          print('INFO took a win ', trades[-1])

    if not traded_today:
      unreal_pnl = my_position[0] * (close_price[0] - my_vwap[0]) * contracts[0].TickValue +\
                   my_position[1] * (close_price[1] - my_vwap[1]) * contracts [1].TickValue
      trades.append([date[0], '-', my_position[2], close_price[2], 0, my_pnl[2] + unreal_pnl, vol[2], ma[2], dev_from_ma, high_price[2], low_price[2]])

  return 0, syn_contract, trades
