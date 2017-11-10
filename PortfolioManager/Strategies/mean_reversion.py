import statistics
import ContractDef.contract_info as ci
import FileUtil.file_parser as fp
import Plots.plots as plots
import matplotlib.pyplot as plt

def MeanReversionStrategy(contract, data_csv='', data_list=[], **strategy_params):
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
    return -1, None

  if data_csv and data_list:
    if log_level > 0:
      print('ERROR cant have both datafile and datalist')
    return -1, None

  # get an iterable based on arguments passed
  market_data = data_list or open(data_csv, 'r')
  if log_level > 0:
    print('INFO opened data file/list ', market_data)

  # dump out trading parameters
  if log_level > 0:
    print('INFO trading params ', strategy_params)

  # pull out parameters, use defaults if missing
  ma_lookback_days = int(strategy_params.pop('ma_lookback_days', 10))
  o_loss_ticks = float(strategy_params.pop('loss_ticks', 5.0))
  o_net_change = float(strategy_params.pop('net_change', 5.0))
  risk_dollars = float(strategy_params.pop('risk_dollars', 1000.0))

  # define some model specific variables
  lookback_prices = [] # maintain, update ma
  my_position, my_vwap, my_pnl = 0, 0, 0 # position, position vwap, pnl

  for line in reversed(list(market_data)): # file is backwards
    try:
      # unpack list
      date, open_price, high_price, low_price, close_price =\
        fp.TokenizeToPriceInfo(contract, line)
    except ValueError or TypeError:
      continue

    lookback_prices.append([high_price, low_price, close_price])

    if len(lookback_prices) < ma_lookback_days + 1:
      # not initialized yet, push and continue
      continue

    # save ma and update list
    # print(list(row[2] for row in lookback_prices))
    ma = statistics.mean(row[2] for row in lookback_prices)
    vol = statistics.mean((row[0] - row[1]) for row in lookback_prices)

    loss_ticks = o_loss_ticks * vol
    net_change = o_net_change * vol
    if log_level > 0:
      print('INFO vol:', vol, 'adjusted params:',
            'net_change:', net_change, 'loss_ticks:', loss_ticks,
            sep=' ')

    lookback_prices.pop(0)
    dev_from_ma = close_price - ma
    if log_level > 0:
      print ('INFO ma:', ma, 'close_price:', close_price, 'dev_from_ma:', dev_from_ma, sep=' ')

    traded_today = False

    if my_position == 0: # flat, see if we want to get into a position
      # how much did today's close price deviate from moving average ?
      # +ve value means breaking out to the upside
      # -ve value means breaking out to the downside
      if abs(dev_from_ma) > net_change: # blown out
        trade_size = int((risk_dollars / contract.TickValue) / loss_ticks + 1)
        my_position = trade_size * (1 if dev_from_ma < 0 else -1)
        my_vwap = close_price
        trades.append([date,('B' if dev_from_ma < 0 else 'S'), trade_size, close_price, my_position, my_pnl, vol, ma, dev_from_ma, high_price, low_price])
        traded_today = True

        if log_level > 0:
          print('INFO initiating position ', trades[-1])
    else: # have a position already, check for stop outs
      if ((my_position > 0 and my_vwap - low_price > loss_ticks) or
          (my_position < 0 and high_price - my_vwap > loss_ticks)):
        stopout_price = my_vwap +\
                        (loss_ticks * (1 if my_position < 0 else -1))
        trade_pnl = abs(my_position) * loss_ticks * contract.TickValue
        my_pnl -= trade_pnl
        buysell = ('S' if my_position > 0 else 'B')

        trades.append([date, buysell, abs(my_position), stopout_price, 0, my_pnl, vol, ma, dev_from_ma, high_price, low_price])
        traded_today = True
        my_position = 0

        if log_level > 0:
          print('INFO stopped out ', trades[-1])
      elif abs(dev_from_ma) < 0.5 * net_change: # trend dying out
        stopout_price = close_price
        trade_pnl = my_position * (stopout_price - my_vwap) * contract.TickValue
        my_pnl += trade_pnl
        buysell = ('S' if my_position > 0 else 'B')

        trades.append (
          [date, buysell, abs (my_position), stopout_price, 0, my_pnl, vol, ma, dev_from_ma, high_price, low_price])
        traded_today = True
        my_position = 0

        if log_level > 0:
          print('INFO took a win ', trades[-1])

    if not traded_today:
      unreal_pnl = my_position * (close_price - my_vwap) * contract.TickValue
      trades.append (
        [date, '-', 0, close_price, my_position, my_pnl + unreal_pnl, vol, ma,
         dev_from_ma, high_price, low_price])

  return 0, trades
