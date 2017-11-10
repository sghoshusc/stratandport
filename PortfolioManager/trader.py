from enum import Enum
import statistics
import Strategies.FileUtil.file_parser as fp
import Strategies.ContractDef.contract_info as ci
import Strategies.DateDef.date_util as dt
import math
import numpy

class TradingStyle(Enum):
  NoTrading = -1
  TrendFollowTrading = 0
  MeanReversionTrading = 1
  RelativeValueTrading = 2
  PairsTrading = 3

"""
This class holds information about individual traders.
:name for plotting/indexing purposes
:trades maintains a list of all trades, plotting & analysis reasons
:alloc is a list of risk changes across the days
:avg_pnl is a shortcut to average pnl since inception
:sum_pnl is a shortcut to sum pnl since inception
:stdev_pnl is deviation on that pnl series
:sharpe is avg/stdev
:num_days is number of days strategy was ready and could have traded
:contracts is either a single contract or a list of 2 contracts for Pairs/Relative
"""
class Trader:
  def __init__(self, contracts, strategy_params):
    self.style = TradingStyle.NoTrading
    self.trades = []
    self.daily_pnl = []
    self.pct_pnl_change = []
    self.alloc = []
    self.stdev_pnl = 1
    self.sharpe = 0
    self.num_days = 0
    self.contracts = contracts
    self.my_position = 0
    self.my_vwap = 0
    self.my_pnl = 0
    self.lookback_prices = []

    # pull out parameters, use defaults if missing
    t_params = dict(strategy_params)
    self.log_level = t_params.pop('log_level', 0)
    self.ma_lookback_days = int(t_params.pop('ma_lookback_days', 40))
    self.o_loss_ticks = float(t_params.pop('loss_ticks', 5.0))
    self.o_net_change = float(t_params.pop('net_change', 5.0))
    self.min_correlation = float(t_params.pop('min_correlation', 0.75))

  def DailyAvgPnl(self):
    return statistics.mean(self.daily_pnl)

  def LastMonthPnl(self):
    return sum(self.daily_pnl[-29:])

  def DailyPnlStdev(self):
    return statistics.stdev(self.daily_pnl)

  def DailyDownsidePnlStdev(self):
    return statistics.stdev(list(min(0, pnl) for pnl in self.daily_pnl))

  def Sharpe(self):
    try:
      ratio = (self.DailyAvgPnl()/self.DailyPnlStdev())
    except ZeroDivisionError:
      ratio = 1

    return ratio

  def Sortino(self):
    try:
      ratio = (self.DailyAvgPnl()/self.DailyDownsidePnlStdev())
    except ZeroDivisionError:
      ratio = 1

    return ratio

  def __str__(self):
    return ('Trader: [' + str(self.Name()) + ' log:' + str(self.log_level)
            + ' ma_look:' + str(self.ma_lookback_days) + ' oloss:' + str(self.o_loss_ticks)
            + ' onetchng:' + str(self.o_net_change) + ' mincor:' + str(self.min_correlation) + ']')

  def Name(self):
    return (str(self.style) + '|' + str(self.contracts))

  def ShortName(self):
    return self.Name().strip().split('.')[-1]

  def ContractList(self):
    return self.contracts

  def ShcToContract(self, shc):
    return ci.ContractInfoDatabase[shc]

  """
  Takes one or more lines of market data & a 
  risk parameter - the risk is dynamically handed down by the portfolio manager now
  """
  def OnMarketDataUpdate(self, contract, date, line, risk_dollars):
    if contract not in self.contracts:
      print('ERROR: ' + contract + ' not in ' + self.contracts)

    # print(self.Name() + ' called with ' + contract + ' ' + date + ' ' + line)

"""
Run a trend following strategy on either the data_csv file
or the data_list list, if both are passed, I will return error.

Trading parameters:
net_change:         how much does today's price have to deviate from
                    ma to consider trend to be starting
ma_lookback_days:   how many days to build moving average over

:param strategy_params: dictionary of trading parameters
"""
class TrendFollowTrader(Trader):
  def __init__(self, contracts, strategy_params):
    Trader.__init__(self, contracts, strategy_params)
    self.style = TradingStyle.TrendFollowTrading

  def OnMarketDataUpdate(self, shc, date, line, risk_dollars):
    Trader.OnMarketDataUpdate(self, shc, date, line, risk_dollars)

    contract = Trader.ShcToContract(self, shc)
    try:
      # unpack list
      date, open_price, high_price, low_price, close_price =\
        fp.TokenizeToPriceInfo(contract, line)
    except ValueError or TypeError:
      return

    self.lookback_prices.append([high_price, low_price, close_price])

    if len(self.lookback_prices) < self.ma_lookback_days + 1:
      # not initialized yet, push and continue
      return

    # save ma and update list
    ma = statistics.mean(row[2] for row in self.lookback_prices)
    vol = statistics.mean((row[0] - row[1]) for row in self.lookback_prices)

    loss_ticks = self.o_loss_ticks * vol
    net_change = self.o_net_change * vol

    if self.log_level > 0:
      print('INFO vol:', vol, 'adjusted params:',
            'net_change:', net_change, 'loss_ticks:', loss_ticks,
            sep=' ')

    self.lookback_prices.pop(0)
    dev_from_ma = close_price - ma
    if self.log_level > 0:
      print ('INFO ma:', ma, 'close_price:', close_price, 'dev_from_ma:', dev_from_ma, sep=' ')

    traded_today = False

    if self.my_position == 0: # flat, see if we want to get into a position
      # how much did today's close price deviate from moving average ?
      # +ve value means breaking out to the upside
      # -ve value means breaking out to the downside
      if abs(dev_from_ma) > net_change: # trend starting
        trade_size = int((risk_dollars / contract.TickValue) / loss_ticks + 1)
        self.my_position = trade_size * (1 if dev_from_ma > 0 else -1)
        self.my_vwap = close_price
        self.trades.append([date,('B' if dev_from_ma > 0 else 'S'), trade_size, close_price, self.my_position, self.my_pnl, vol, ma, dev_from_ma, high_price, low_price])
        traded_today = True

        if self.log_level > 0:
          print('INFO initiating position ', self.trades[-1])
    else: # have a position already, check for stop outs
      if ((self.my_position > 0 and self.my_vwap - low_price > loss_ticks) or
          (self.my_position < 0 and high_price - self.my_vwap > loss_ticks)):
        stopout_price = self.my_vwap +\
                        (loss_ticks * (1 if self.my_position < 0 else -1))
        trade_pnl = abs(self.my_position) * loss_ticks * contract.TickValue
        self.my_pnl -= trade_pnl
        buysell = ('S' if self.my_position > 0 else 'B')

        self.trades.append([date, buysell, abs(self.my_position), stopout_price, 0, self.my_pnl, vol, ma, dev_from_ma, high_price, low_price])
        traded_today = True
        self.my_position = 0

        if self.log_level > 0:
          print('INFO stopped out ', self.trades[-1])
      elif abs(dev_from_ma) < 0.5 * net_change: # trend dying out
        stopout_price = close_price
        trade_pnl = self.my_position * (stopout_price - self.my_vwap) * contract.TickValue
        self.my_pnl += trade_pnl
        buysell = ('S' if self.my_position > 0 else 'B')

        self.trades.append (
          [date, buysell, abs (self.my_position), stopout_price, 0, self.my_pnl, vol, ma, dev_from_ma, high_price, low_price])
        traded_today = True
        self.my_position = 0

        if self.log_level > 0:
          print('INFO took a win ', self.trades[-1])

    # add an empty line if no self.trades were made today otherwise you'll see gaps in plots
    if not traded_today:
      unreal_pnl = self.my_position * (close_price - self.my_vwap) * contract.TickValue
      self.trades.append (
        [date, '-', 0, close_price, self.my_position, self.my_pnl + unreal_pnl, vol, ma,
         dev_from_ma, high_price, low_price])

    self.alloc.append(risk_dollars)
    if len(self.trades) >= 2:
      self.daily_pnl.append(self.trades[-1][5] - self.trades[-2][5])
      if self.trades[-2][5] != 0:
        self.pct_pnl_change.append(100 * self.daily_pnl[-1]/abs(self.trades[-2][5])) # what % pnl increase?
    else:
      self.daily_pnl.append(self.trades[-1][5])


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
class MeanReversionTrader(Trader):
  def __init__(self, contracts, strategy_params):
    Trader.__init__(self, contracts, strategy_params)
    self.style = TradingStyle.MeanReversionTrading

  def OnMarketDataUpdate(self, shc, date, line, risk_dollars):
    Trader.OnMarketDataUpdate(self, shc, date, line, risk_dollars)

    contract = Trader.ShcToContract(self, shc)
    try:
      # unpack list
      date, open_price, high_price, low_price, close_price =\
        fp.TokenizeToPriceInfo(contract, line)
    except ValueError or TypeError:
      return

    self.lookback_prices.append([high_price, low_price, close_price])

    if len(self.lookback_prices) < self.ma_lookback_days + 1:
      # not initialized yet, push and continue
      return

    # save ma and update list
    # print(list(row[2] for row in lookback_prices))
    ma = statistics.mean(row[2] for row in self.lookback_prices)
    vol = statistics.mean((row[0] - row[1]) for row in self.lookback_prices)

    loss_ticks = self.o_loss_ticks * vol
    net_change = self.o_net_change * vol
    if self.log_level > 0:
      print('INFO vol:', vol, 'adjusted params:',
            'net_change:', net_change, 'loss_ticks:', loss_ticks,
            sep=' ')

    self.lookback_prices.pop(0)
    dev_from_ma = close_price - ma
    if self.log_level > 0:
      print ('INFO ma:', ma, 'close_price:', close_price, 'dev_from_ma:', dev_from_ma, sep=' ')

    traded_today = False

    if self.my_position == 0: # flat, see if we want to get into a position
      # how much did today's close price deviate from moving average ?
      # +ve value means breaking out to the upside
      # -ve value means breaking out to the downside
      if abs(dev_from_ma) > net_change: # blown out
        trade_size = int((risk_dollars / contract.TickValue) / loss_ticks + 1)
        self.my_position = trade_size * (1 if dev_from_ma < 0 else -1)
        self.my_vwap = close_price
        self.trades.append([date,('B' if dev_from_ma < 0 else 'S'), trade_size, close_price, self.my_position, self.my_pnl, vol, ma, dev_from_ma, high_price, low_price])
        traded_today = True

        if self.log_level > 0:
          print('INFO initiating position ', self.trades[-1])
    else: # have a position already, check for stop outs
      if ((self.my_position > 0 and self.my_vwap - low_price > loss_ticks) or
          (self.my_position < 0 and high_price - self.my_vwap > loss_ticks)):
        stopout_price = self.my_vwap +\
                        (loss_ticks * (1 if self.my_position < 0 else -1))
        trade_pnl = abs(self.my_position) * loss_ticks * contract.TickValue
        self.my_pnl -= trade_pnl
        buysell = ('S' if self.my_position > 0 else 'B')

        self.trades.append([date, buysell, abs(self.my_position), stopout_price, 0, self.my_pnl, vol, ma, dev_from_ma, high_price, low_price])
        traded_today = True
        self.my_position = 0

        if self.log_level > 0:
          print('INFO stopped out ', self.trades[-1])
      elif abs(dev_from_ma) < 0.5 * net_change: # trend dying out
        stopout_price = close_price
        trade_pnl = self.my_position * (stopout_price - self.my_vwap) * contract.TickValue
        self.my_pnl += trade_pnl
        buysell = ('S' if self.my_position > 0 else 'B')

        self.trades.append (
          [date, buysell, abs (self.my_position), stopout_price, 0, self.my_pnl, vol, ma, dev_from_ma, high_price, low_price])
        traded_today = True
        self.my_position = 0

        if self.log_level > 0:
          print('INFO took a win ', self.trades[-1])

    if not traded_today:
      unreal_pnl = self.my_position * (close_price - self.my_vwap) * contract.TickValue
      self.trades.append (
        [date, '-', 0, close_price, self.my_position, self.my_pnl + unreal_pnl, vol, ma,
         dev_from_ma, high_price, low_price])

    self.alloc.append(risk_dollars)
    if len(self.trades) >= 2:
      self.daily_pnl.append(self.trades[-1][5] - self.trades[-2][5])
      if self.trades[-2][5] != 0:
        self.pct_pnl_change.append(100 * self.daily_pnl[-1]/abs(self.trades[-2][5])) # what % pnl increase?
    else:
      self.daily_pnl.append(self.trades[-1][5])



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
class RelativeValueTrader(Trader):
  def __init__(self, contracts, strategy_params):
    Trader.__init__(self, contracts, strategy_params)
    self.style = TradingStyle.RelativeValueTrading

    self.market_data = [None, None]

    # define some model specific variables
    self.lookback_prices = [[], []]  # maintain, update ma

    self.lookback_dev_from_ma = [[], []]
    self.lookback_dev_from_projection = []

  def OnMarketDataUpdate(self, shc, date, line, risk_dollars):
    Trader.OnMarketDataUpdate(self, shc, date, line, risk_dollars)

    contract_index = (1 if shc == self.contracts[1] else 0)
    self.market_data[contract_index] = line
    if not all(self.market_data):
      return

    contracts = [ci.ContractInfoDatabase[self.contracts[0]], ci.ContractInfoDatabase[self.contracts[1]]]

    date, open_price, high_price, low_price, close_price =\
      [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]
    try:
      # unpack list
      for index in [0, 1]:
        date[index], open_price[index], high_price[index], low_price[index], close_price[index] =\
          fp.TokenizeToPriceInfo(contracts[index], self.market_data[index])
    except ValueError or TypeError:
      return

    if dt.CompareDates(date[0], date[1]) != 0:
      return
    # print(str(self.market_data))

    for index in [0, 1]:
      self.lookback_prices[index].append([high_price[index], low_price[index], close_price[index]])

    if len(self.lookback_prices[0]) < self.ma_lookback_days + 1:
      # not initialized yet, push and continue
      return

    # save ma and update list
    # print(list(row[2] for row in lookback_prices))
    ma, vol, dev_from_ma = [0, 0], [0, 0], [0, 0]
    for index in [0, 1]:
      ma[index] = statistics.mean(row[2] for row in self.lookback_prices[index])
      vol[index] = statistics.mean(abs(row[0] - row[1]) for row in self.lookback_prices[index])
      dev_from_ma[index] = close_price[index] - ma[index]
      self.lookback_dev_from_ma[index].append(dev_from_ma[index])

    # Need at least 2 points, not enough degrees of freedom
    if len(self.lookback_dev_from_ma[0]) < 2:
      return

    corr = numpy.corrcoef(self.lookback_dev_from_ma[0], self.lookback_dev_from_ma[1])
    cov = numpy.cov(self.lookback_dev_from_ma[0], self.lookback_dev_from_ma[1])
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
    if math.isnan(dev_from_projection):
      if self.log_level > 0:
        print('Skipping because dev_from_projection:', dev_from_projection, 'or correlation:', corr_0_1, 'less than', self.min_correlation)
      return

    # track it so we know how big an average deviation is
    self.lookback_dev_from_projection.append(dev_from_projection)  # this measure only cares about the magnitude
    dev_from_projection_vol = statistics.mean(abs(item) for item in self.lookback_dev_from_projection)

    if self.log_level > 0:
      print('dev_from_projection', dev_from_projection, 'dev_from_projection_vol', dev_from_projection_vol, 'entries', self.lookback_dev_from_projection, sep=' ')

    if len(self.lookback_dev_from_ma[0]) < self.ma_lookback_days + 1:
      # need to have a long enough history
      # of relative deviations to project in the future
      if self.log_level > 0:
        print('not enough lookback_dev_from_ma history', len(self.lookback_dev_from_ma[0]), self.ma_lookback_days, sep=' ')
      return

    for index in [0, 1]:
      while len(self.lookback_prices[index]) > self.ma_lookback_days:
        self.lookback_prices[index].pop(0)
      while len(self.lookback_dev_from_ma[index]) > self.ma_lookback_days:
        self.lookback_dev_from_ma[index].pop(0)
    while len(self.lookback_dev_from_projection) > self.ma_lookback_days:
      self.lookback_dev_from_projection.pop(0)

    if self.log_level > 0:
      print(contracts[0].Name, 'projected by', contracts[1].Name, 'correlation:', corr_0_1, 'coefficient:', cov_0_1)
      print('projected_dev_from_ma', projected_dev_from_ma, 'actual', dev_from_ma[0], 'dev_from_projection', dev_from_projection, sep=' ')

    loss_ticks = self.o_loss_ticks * vol[0]
    net_change = self.o_net_change * dev_from_projection_vol

    if self.log_level > 0:
      print('INFO vol:', vol, 'adjusted params:', 'net_change:', net_change, 'loss_ticks:', loss_ticks,
            sep=' ')

    traded_today = False

    if self.my_position == 0: # flat, see if we want to get into a position
      # how much did today's close price deviate from moving average ?
      # +ve value means breaking out to the upside
      # -ve value means breaking out to the downside
      if abs(dev_from_projection) > net_change: # blown out
        trade_size = int((risk_dollars / contracts[0].TickValue) / loss_ticks + 1)
        self.my_position = trade_size * (1 if dev_from_projection > 0 else -1)
        self.my_vwap = close_price[0]
        self.trades.append([date[0],('B' if dev_from_projection > 0 else 'S'), trade_size, close_price[0], self.my_position, self.my_pnl, dev_from_projection_vol, ma[0], dev_from_projection, projected_price, corr_0_1])
        traded_today = True

        if self.log_level > 0:
          print('INFO initiating position ', self.trades[-1])
    else: # have a position already, check for stop outs
      if ((self.my_position > 0 and self.my_vwap - low_price[0] > loss_ticks) or
          (self.my_position < 0 and high_price[0] - self.my_vwap > loss_ticks)):
        stopout_price = self.my_vwap +\
                        (loss_ticks * (1 if self.my_position < 0 else -1))
        trade_pnl = abs(self.my_position) * loss_ticks * contracts[0].TickValue
        self.my_pnl -= trade_pnl
        buysell = ('S' if self.my_position > 0 else 'B')

        self.trades.append([date[0], buysell, abs(self.my_position), stopout_price, 0, self.my_pnl, dev_from_projection_vol, ma[0], dev_from_projection, projected_price, corr_0_1])
        traded_today = True
        self.my_position = 0

        if self.log_level > 0:
          print('INFO stopped out ', self.trades[-1])
      elif abs(dev_from_projection) < 0.5 * net_change: # deviation dying out
        stopout_price = close_price[0]
        trade_pnl = self.my_position * (stopout_price - self.my_vwap) * contracts[0].TickValue
        self.my_pnl += trade_pnl
        buysell = ('S' if self.my_position > 0 else 'B')

        self.trades.append (
          [date[0], buysell, abs (self.my_position), stopout_price, 0, self.my_pnl, vol[0], ma[0], dev_from_projection_vol, projected_price, corr_0_1])
        traded_today = True
        self.my_position = 0

        if self.log_level > 0:
          print('INFO took a win ', self.trades[-1])

    if not traded_today:
      unreal_pnl = self.my_position * (close_price[0] - self.my_vwap) * contracts[0].TickValue
      self.trades.append([date[0], '-', self.my_position, close_price[0], 0, self.my_pnl + unreal_pnl, dev_from_projection_vol, ma[0], dev_from_projection, projected_price, corr_0_1])

    self.alloc.append(risk_dollars)
    if len(self.trades) >= 2:
      self.daily_pnl.append(self.trades[-1][5] - self.trades[-2][5])
      if self.trades[-2][5] != 0:
        self.pct_pnl_change.append(100 * self.daily_pnl[-1]/abs(self.trades[-2][5])) # what % pnl increase?
    else:
      self.daily_pnl.append(self.trades[-1][5])



    if self.log_level > 0:
      print('TRADE ' + str(self.ShortName()) + ' ' + str(self.trades[-1]))
      print('ALLOC ' + str(self.ShortName()) + ' ' + str(self.alloc[-1]))

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
class PairsTrader(Trader):
  def __init__(self, contracts, strategy_params):
    Trader.__init__(self, contracts, strategy_params)
    self.style = TradingStyle.PairsTrading
    self.syn_contract = None
    self.market_data = [None, None]

    # define some model specific variables
    self.lookback_prices = [[], [], []]  # maintain, update ma
    self.my_position, self.my_vwap, self.my_pnl =\
      [0, 0, 0], [0, 0, 0], [0, 0, 0]  # position, position vwap, pnl

  def DailyAvgPnl(self):
    return (self.my_pnl[0] + self.my_pnl[1]) / len(self.trades) if len(self.trades) > 0 else 0

  def ComputeSpreadPrice(self, ratio, is_inverted, price_1, price_2):
    # basic idea is to multiply the leg with lower dollar volatility
    # with a higher ratio to get the correct hedge size
    spread_price = price_1 - price_2 * ratio
    if is_inverted:
      spread_price = price_1 * ratio - price_2

    # print('INFO price_1, price_2, ratio, spread_price, is_inverted ', price_1, price_2, ratio, spread_price, is_inverted)
    return spread_price

  def OnMarketDataUpdate(self, shc, date, line, risk_dollars):
    Trader.OnMarketDataUpdate(self, shc, date, line, risk_dollars)

    contract_index = (1 if shc == self.contracts[1] else 0)
    self.market_data[contract_index] = line
    if not all(self.market_data):
      return

    contracts = [ci.ContractInfoDatabase[self.contracts[0]], ci.ContractInfoDatabase[self.contracts[1]]]
    contracts.append(ci.ContractInfo(contracts[0].Name + ' VS. ' + contracts[1].Name, 0.01, 10))

    date, open_price, high_price, low_price, close_price =\
      [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]
    try:
      # unpack list
      for index in [0, 1]:
        date[index], open_price[index], high_price[index], low_price[index], close_price[index] =\
          fp.TokenizeToPriceInfo(contracts[index], self.market_data[index])
    except ValueError or TypeError:
      return

    if dt.CompareDates(date[0], date[1]) != 0:
      return
    # print(str(self.market_data))

    for index in [0, 1]:
      self.lookback_prices[index].append([high_price[index], low_price[index], close_price[index]])

    if len(self.lookback_prices[0]) < self.ma_lookback_days + 1:
      # not initialized yet, push and continue
      return

    # save ma and update list
    # print(list(row[2] for row in lookback_prices))
    ma, vol, dollar_vol, weight = [0, 0, 0], [0, 0, 0], [0, 0, 0], [1, 1, 1]
    for index in [0, 1]:
      ma[index] = statistics.mean(row[2] for row in self.lookback_prices[index])
      vol[index] = statistics.mean(abs(row[0] - row[1]) for row in self.lookback_prices[index])
      dollar_vol[index] = vol[index] * contracts[index].TickValue

    is_inverted = False # maintain a flag if we invert ratio
    ratio = dollar_vol[0] / dollar_vol[1]
    if ratio < 1:
      ratio = 1 / ratio
      is_inverted = True

    high_price[2] = self.ComputeSpreadPrice(ratio, is_inverted, high_price[0], high_price[1])
    low_price[2] = self.ComputeSpreadPrice(ratio, is_inverted, low_price[0], low_price[1])
    close_price[2] = self.ComputeSpreadPrice(ratio, is_inverted, close_price[0], close_price[1])
    self.lookback_prices[2].append([high_price[2], low_price[2], close_price[2]])
    ma[2] = statistics.mean(row[2] for row in self.lookback_prices[2])
    vol[2] = statistics.mean(abs(row[0] - row[1]) for row in self.lookback_prices[2])
    dev_from_ma = close_price[2] - ma[2]

    if self.log_level > 0:
      print('INFO vol ', vol, ' dollar vol ', dollar_vol, ' ratio ', ratio)

    for index in [0, 1, 2]:
      if len(self.lookback_prices[index]) >= self.ma_lookback_days:
        self.lookback_prices[index].pop(0)

    loss_ticks = self.o_loss_ticks * vol[2]
    net_change = self.o_net_change * vol[2]

    # this is a tough one, and this solution is imperfect
    # but preferred for its simplicity
    spread_tick_value = min(contracts[0].TickValue, contracts[1].TickValue * ratio)
    if is_inverted:
      spread_tick_value = min(contracts[0].TickValue * ratio, contracts[1].TickValue)

    if self.log_level > 0:
      print('INFO vol:', vol, 'adjusted params:', 'net_change:', net_change, 'loss_ticks:', loss_ticks,
            'spread_tick_value:', spread_tick_value, sep=' ')

    traded_today = False

    if self.my_position[2] == 0: # flat, see if we want to get into a position
      # how much did today's close price deviate from moving average ?
      # +ve value means breaking out to the upside
      # -ve value means breaking out to the downside
      if abs(dev_from_ma) > net_change: # blown out
        trade_size = int((risk_dollars / spread_tick_value) / loss_ticks + 1)
        self.my_position[0] = trade_size * (ratio if is_inverted else 1)
        self.my_position[1] = trade_size * (1 if is_inverted else ratio)
        self.my_vwap = list(close_price)
        self.my_position[2] = trade_size * (1 if dev_from_ma < 0 else -1)
        self.my_vwap[2] = close_price[2]
        self.trades.append([date[0], ('B' if dev_from_ma < 0 else 'S'), trade_size, close_price[2],
                       self.my_position[2], self.my_pnl[2], vol[2], ma[2], dev_from_ma, high_price[2], low_price[2]])
        traded_today = True

        if self.log_level > 0:
          print('INFO initiating position ', self.trades[-1])
    else: # have a position already, check for stop outs
      if ((self.my_position[2] > 0 and self.my_vwap[2] - low_price[2] > loss_ticks) or
          (self.my_position[2] < 0 and high_price[2] - self.my_vwap[2] > loss_ticks)):
        stopout_price = self.my_vwap[2] +\
                        (loss_ticks * (1 if self.my_position[2] < 0 else -1))
        trade_pnl = abs(self.my_position[2]) * loss_ticks * spread_tick_value
        self.my_pnl[2] -= trade_pnl
        buysell = ('S' if self.my_position[2] > 0 else 'B')

        self.trades.append([date[0], buysell, abs(self.my_position[2]), stopout_price, 0, self.my_pnl[2], vol[2], ma[2], dev_from_ma, high_price[2], low_price[2]])
        traded_today = True
        self.my_position = [0, 0, 0]

        if self.log_level > 0:
          print('INFO stopped out ', self.trades[-1])
      elif abs(dev_from_ma) < 0.5 * net_change: # trend dying out
        self.my_pnl[0] += self.my_position[0] * (close_price[0] - self.my_vwap[0]) * contracts[0].TickValue
        self.my_pnl[1] += self.my_position[1] * (close_price[1] - self.my_vwap[1]) * contracts[1].TickValue
        self.my_pnl[2] = self.my_pnl[0] + self.my_pnl[1]
        buysell = ('S' if self.my_position[2] > 0 else 'B')

        self.trades.append (
          [date[0], buysell, abs(self.my_position[2]), close_price[2], 0, self.my_pnl[2], vol[2], ma[2], dev_from_ma, high_price[2], low_price[2]])
        traded_today = True
        self.my_position = [0, 0, 0]

        if self.log_level > 0:
          print('INFO took a win ', self.trades[-1])

    if not traded_today:
      unreal_pnl = self.my_position[0] * (close_price[0] - self.my_vwap[0]) * contracts[0].TickValue +\
                   self.my_position[1] * (close_price[1] - self.my_vwap[1]) * contracts [1].TickValue
      self.trades.append([date[0], '-', self.my_position[2], close_price[2], 0, self.my_pnl[2] + unreal_pnl, vol[2], ma[2], dev_from_ma, high_price[2], low_price[2]])

    self.alloc.append(risk_dollars)
    if len(self.trades) >= 2:
      self.daily_pnl.append(self.trades[-1][5] - self.trades[-2][5])
      if self.trades[-2][5] != 0:
        self.pct_pnl_change.append(100 * self.daily_pnl[-1]/abs(self.trades[-2][5])) # what % pnl increase?
    else:
      self.daily_pnl.append(self.trades[-1][5])

