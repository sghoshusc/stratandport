import sys, statistics, numpy, cvxopt, functools
from cvxopt import blas, solvers
from enum import Enum
import Strategies.Plots.plots as plt
import Strategies.ContractDef.contract_info as ci
import Strategies.DateDef.date_util as dt

# this is how much a trader gets as starting allocation
FIRST_ALLOCATION = 10000

# minimum & maximum allowed allocations irrespective of any metric
MIN_ALLOCATION = 1000
MAX_ALLOCATION = 200000

# this is total per day allocation this PM gets
TOTAL_ALLOCATION = 420000

# reallocate risk every these many days
NUM_DAYS_TO_RECALIBRATE = 28 # once a month

class AllocationStyle(Enum):
  NoAlloc = -1
  UniformAlloc = 0          # Give everyone 'x' risk and let them run till end of time
  HCTAlloc = 1              # double winners, halve losers every week
  IndividualPnlAlloc = 2    # he who made more money gets more money
  IndividualSharpeAlloc = 3 # he who had better risk normalized pnls, gets more money
  IndividualSortinoAlloc = 4# he who had better risk normalized pnls, gets more money
  MarkowitzAlloc = 5        # combine traders to minimize overall portfolio risk
  MLPredictiveAlloc = 6     # learn from past return patterns
  RegimePredictiveAlloc = 7 # use economic indicators to predict future returns
                            # of each strategy and then find a combination accordingly

class PortfolioManager:
  def __init__(self):
    self.style = AllocationStyle.NoAlloc

    # map from trader id to trading history information
    # like allocations, strategy description, trades, pnls, sharpe
    self.traders = {}
    self.alloc = {} # this will overtime with trader performance

    self.num_updates = 0

    # when was the last time we judged trader performance?
    # we re-assess allocations every 10 days
    self.last_recal_date = None

    # this will get updated after market update,
    # so we know how much data we can retrain model on and make predictions from.
    # without this check I'd be cheating because of look ahead.
    # i.e. on 20170505, i am allowed to look at all data before 20170505
    self.last_date_index = 0
    self.last_date = None

  def AddTrader(self, trader):
    self.traders[trader.Name()] = trader
    self.alloc[trader.Name()] = FIRST_ALLOCATION # initial alloc for all PM

  def RecalibrateAllocations(self):
    raise NotImplementedError

  def OnMarketDataUpdate(self, shc, date, line):
    self.last_date = date

    self.num_updates += 1
    if self.num_updates % 1000 == 0:
      print('|', end='')
      sys.stdout.flush()

    # cycle through every trader under management
    for name in self.traders.keys():
      # check if trader cares about this contract
      if shc in self.traders[name].ContractList():
        # notify them of market update
        self.traders[name].OnMarketDataUpdate(shc, date, line, self.alloc[name])

    if not self.last_recal_date:
      self.last_recal_date = date
      return

    if dt.NumDaysBetween(self.last_recal_date, date) >= NUM_DAYS_TO_RECALIBRATE:
      self.RecalibrateAllocations()
      self.last_recal_date = date
      self.CheckAllocations()

  def CheckAllocations(self):
    total_alloc = sum(self.alloc.values())
    for trader in self.alloc:
      self.alloc[trader] = (self.alloc[trader] * TOTAL_ALLOCATION) / total_alloc

    total_alloc = sum(self.alloc.values())
    if not TOTAL_ALLOCATION * 0.99 < total_alloc < TOTAL_ALLOCATION * 1.01:
      print(str(self) + ' under/over allocation! total: ' + str(total_alloc) + ' limit: ' + str(TOTAL_ALLOCATION))
      exit(0)

  def __str__(self):
    return 'Portfolio manager: ' + str(self.style) + '|' + str(len(self.traders))

  def SummarizePerformance(self):
    print('  Summarizing: ' + str(self))
    print('    ' + format('Trader', '35s')
          + ' ' + format('FinalPnl(mil$)', '10s')
          + ' ' + format('AvgPnl(K$)', '10s')
          + ' ' + format('Sharpe', '10s')
          + ' ' + format('Sortino', '10s')
          + ' ' + format('PnlStdev(K$)', '10s')
          + ' ' + format('PnlDownStdev(K$)', '10s')
          + ' ' + format('FinalAlloc(K$)', '10s'))
    for trader in self.traders.keys():
      print('    ' + format(self.traders[trader].ShortName(), '35s')
            + ' ' + str(format(self.traders[trader].trades[-1][5]/1000000.0, '10.3f'))
            + ' ' + str(format(self.traders[trader].DailyAvgPnl()/1000.0, '10.3f'))
            + ' ' + str(format(self.traders[trader].Sharpe(), '10.7f'))
            + ' ' + str(format(self.traders[trader].Sortino(), '10.7f'))
            + ' ' + str(format(self.traders[trader].DailyPnlStdev()/1000.0, '10.3f'))
            + ' ' + str(format(self.traders[trader].DailyDownsidePnlStdev()/1000.0, '10.3f'))
            + ' ' + str(format(self.traders[trader].alloc[-1]/1000.0, '10.3f')))

    self.PlotAllocationsAndPnls()

    daily_pnl_list = [self.pnl_list[0]] # initial is first day of pnl
    for i in range(1, len(self.pnl_list)):
      daily_pnl_list.append(self.pnl_list[i] - self.pnl_list[i-1])
    self.avg_pnl = statistics.mean(daily_pnl_list)
    self.stdev_pnl = statistics.stdev(daily_pnl_list)
    down_stdev_pnl = statistics.stdev(min(0, pnl) for pnl in daily_pnl_list)

    print('    ' + format('PM', '35s')
          + ' ' + format('FinalPnl(mil$)', '10s')
          + ' ' + format('AvgPnl(K$)', '10s')
          + ' ' + format('Sharpe', '10s')
          + ' ' + format('Sortino', '10s')
          + ' ' + format('PnlStdev(K$)', '10s')
          + ' ' + format('PnlDownStdev(K$)', '10s'))
    print('    ' + format(str(self.style), '35s')
          + ' ' + str(format(self.pnl_list[-1]/1000000.0, '10.3f'))
          + ' ' + str(format(self.avg_pnl/1000.0, '10.3f'))
          + ' ' + str(format(self.avg_pnl/self.stdev_pnl, '10.7f'))
          + ' ' + str(format(self.avg_pnl/down_stdev_pnl, '10.7f'))
          + ' ' + str(format(self.stdev_pnl/1000.0, '10.3f'))
          + ' ' + str(format(down_stdev_pnl/1000.0, '10.3f')))

  def PlotAllocationsAndPnls(self):
    self.shortcode_results, self.shortcode_allocs = {}, {}
    for trader in self.traders.keys():
      self.shortcode_results[(self.traders[trader]).Name()] = list(self.traders[trader].trades)
      self.shortcode_allocs[(self.traders[trader]).Name()] = list(self.traders[trader].alloc)

    self.all_dates, self.pnl_list = plt.MergeAndPlotTradesAndAlloc(str(self.style), self.shortcode_results, self.shortcode_allocs, ci.ContractInfoDatabase)

class UniformAllocPM(PortfolioManager):
  def __init__(self):
    PortfolioManager.__init__(self)
    self.style = AllocationStyle.UniformAlloc

  def RecalibrateAllocations(self):
    # This is the baseline PM
    # Always hand out equal allocation regardless of performance/prediction
    for trader in self.alloc:
      self.alloc[trader] = TOTAL_ALLOCATION/len(self.alloc)

class HCTAllocPM(PortfolioManager):
  def __init__(self):
    PortfolioManager.__init__(self)
    self.style = AllocationStyle.HCTAlloc

  def RecalibrateAllocations(self):
    for trader in self.alloc:
      if len(self.traders[trader].trades) >= 2 * NUM_DAYS_TO_RECALIBRATE:
        scale_factor = 3 if self.traders[trader].LastMonthPnl() > 0 else 0.33
        new_alloc = min(max(int(self.alloc[trader] * scale_factor), MIN_ALLOCATION), MAX_ALLOCATION)
        self.alloc[trader] = new_alloc

    # scale allocations so that we are within limits
    total_allocation = sum(self.alloc.values())
    for trader in self.alloc:
      self.alloc[trader] = int((self.alloc[trader] * TOTAL_ALLOCATION) / total_allocation)

class IndividualPnlAllocPM(PortfolioManager):
  def __init__(self):
    PortfolioManager.__init__(self)
    self.style = AllocationStyle.IndividualPnlAlloc

  def RecalibrateAllocations(self):
    # This PM looks at average daily returns and assigns risk accordingly
    sum_avg_pnl = 0
    traders_to_alloc = []
    total_allocation = TOTAL_ALLOCATION

    for trader in self.alloc:
      if len(self.traders[trader].trades) >= 2 * NUM_DAYS_TO_RECALIBRATE:
        if self.traders[trader].DailyAvgPnl() < 0:
          # losing, cut risk
          new_alloc = max(int(self.alloc[trader] * 0.9), MIN_ALLOCATION)
          self.alloc[trader] = new_alloc
          total_allocation -= new_alloc
        else:
          sum_avg_pnl += (self.traders[trader].DailyAvgPnl())
          traders_to_alloc.append(trader)
      else:
        # trader has traded for inadequate amount of time, too soon to gauge performance
        total_allocation -= self.alloc[trader]

    for trader in traders_to_alloc:
      prop_alloc = int((self.traders[trader].DailyAvgPnl() * total_allocation) / sum_avg_pnl)
      prop_alloc = min(max(prop_alloc, MIN_ALLOCATION), MAX_ALLOCATION)
      self.alloc[trader] = prop_alloc

class IndividualSharpeAllocPM(PortfolioManager):
  def __init__(self):
    PortfolioManager.__init__(self)
    self.style = AllocationStyle.IndividualSharpeAlloc

  def RecalibrateAllocations(self):
    # This PM looks at average daily returns and assigns risk accordingly
    sum_avg_pnl_stdev = 0
    traders_to_alloc = []
    total_allocation = TOTAL_ALLOCATION

    for trader in self.alloc:
      if len(self.traders[trader].trades) >= 2 * NUM_DAYS_TO_RECALIBRATE:
        if self.traders[trader].Sharpe() < 0:
          # losing, cut risk
          new_alloc = max(int(self.alloc[trader] * 0.9), MIN_ALLOCATION)
          self.alloc[trader] = new_alloc
          total_allocation -= new_alloc
        else:
          sum_avg_pnl_stdev += (self.traders[trader].Sharpe())
          traders_to_alloc.append(trader)
      else:
        # trader has traded for inadequate amount of time, too soon to gauge performance
        total_allocation -= self.alloc[trader]

    for trader in traders_to_alloc:
      prop_alloc = int((self.traders[trader].Sharpe() * total_allocation) / sum_avg_pnl_stdev)
      prop_alloc = min(max(prop_alloc, MIN_ALLOCATION), MAX_ALLOCATION)
      self.alloc[trader] = prop_alloc

class IndividualSortinoAllocPM(PortfolioManager):
  def __init__(self):
    PortfolioManager.__init__(self)
    self.style = AllocationStyle.IndividualSortinoAlloc

  def RecalibrateAllocations(self):
    # This PM looks at average daily returns and assigns risk accordingly
    sum_avg_pnl_stdev = 0
    traders_to_alloc = []
    total_allocation = TOTAL_ALLOCATION

    for trader in self.alloc:
      if len(self.traders[trader].trades) >= 2 * NUM_DAYS_TO_RECALIBRATE:
        if self.traders[trader].Sortino() < 0:
          # losing, cut risk
          new_alloc = max(int(self.alloc[trader] * 0.9), MIN_ALLOCATION)
          self.alloc[trader] = new_alloc
          total_allocation -= new_alloc
        else:
          sum_avg_pnl_stdev += (self.traders[trader].Sortino())
          traders_to_alloc.append(trader)
      else:
        # trader has traded for inadequate amount of time, too soon to gauge performance
        total_allocation -= self.alloc[trader]

    for trader in traders_to_alloc:
      prop_alloc = int((self.traders[trader].Sortino() * total_allocation) / sum_avg_pnl_stdev)
      prop_alloc = min(max(prop_alloc, MIN_ALLOCATION), MAX_ALLOCATION)
      self.alloc[trader] = prop_alloc

class MarkowitzAllocPM(PortfolioManager):
  def __init__(self):
    PortfolioManager.__init__(self)
    self.style = AllocationStyle.MarkowitzAlloc

  def RecalibrateAllocations(self):
    traders_to_alloc = []
    total_allocation = TOTAL_ALLOCATION

    for trader in self.alloc:
      if len(self.traders[trader].trades) >= 2 * NUM_DAYS_TO_RECALIBRATE:
        traders_to_alloc.append(trader)
      else:
        # trader has traded for inadequate amount of time, too soon to gauge performance
        total_allocation -= self.alloc[trader]

    if len(traders_to_alloc) <= 0:
      return

    # generate a returns matrix
    trader_index = {} # map from index to trader object in returns matrix
    returns = []
    min_length = None
    for trader in traders_to_alloc:
      trader_index[len(returns)] = trader
      returns.append(self.traders[trader].pct_pnl_change)
      min_length = len(returns[-1]) if not min_length else min(min_length, len(returns[-1]))

    # make sure lists are same length
    for index in range(0, len(returns)):
      returns[index] = returns[index][:min_length]

    returns = numpy.matrix(returns)
    # print(str(returns))

    # optimize for mean variance, gets weights
    # assign weights back to alloc
    try:
      weights = self.OptimizePortfolio(returns)
    except:
      return

    sum_weights = sum(weights)
    for index in range(0, len(weights)):
      trader = trader_index[index]
      self.alloc[trader] = (weights[index] / sum_weights) * total_allocation

    # print(str(sum_weights) + ' ' + str(weights))

  def OptimizePortfolio(self, returns):
    n = len(returns)
    returns = numpy.asmatrix(returns)

    N = 100
    mus = [10**(5.0 * t/N - 1.0) for t in range(N)]

    # Convert to cvxopt matrices
    S = cvxopt.matrix(numpy.cov(returns))
    pbar = cvxopt.matrix(numpy.mean(returns, axis=1))

    # Create constraint matrices
    G = -cvxopt.matrix(numpy.eye(n))  # negative n x n identity matrix
    h = cvxopt.matrix(0.0, (n, 1))
    A = cvxopt.matrix(1.0, (1, n))
    b = cvxopt.matrix(1.0)

    solvers.options['show_progress'] = False
    # Calculate efficient frontier weights using quadratic programming
    portfolios = [solvers.qp(mu * S, -pbar, G, h, A, b)['x']
                  for mu in mus]

    # CALCULATE RISKS AND RETURNS FOR FRONTIER
    returns = [blas.dot(pbar, x) for x in portfolios]
    risks = [numpy.sqrt(blas.dot(x, S * x)) for x in portfolios]

    # CALCULATE THE 2ND DEGREE POLYNOMIAL OF THE FRONTIER CURVE
    m1 = numpy.polyfit(returns, risks, 2)
    x1 = numpy.sqrt(m1[2] / m1[0])

    # CALCULATE THE OPTIMAL PORTFOLIO
    wt = solvers.qp(cvxopt.matrix(x1 * S), -pbar, G, h, A, b)['x']
    wt = numpy.asarray(wt)

    wt = wt.tolist()
    for index in range(0, len(wt)):
      wt[index] = wt[index][0]
    return wt

class RegimePredictiveAllocPM(PortfolioManager):
  def __init__(self):
    PortfolioManager.__init__(self)
    self.style = AllocationStyle.RegimePredictiveAlloc
    self.trader_pnl_series = {}
    self.LoadIndicatorData()

    # x [m x n] matrix
    # [ [d1, I11, I12, I13, I14....I1n],
    #   [d2, I21, I22, I23, I24....I2n],
    #   ...............................
    #   [dm, Im1, Im2, Im3, Im4....Imn] ]
    self.x = [] # one row for each date, length of row is how many indicators we use

    # y [m x 43] matrix
    # [ [d1, r11, r12, r13, r14....r142],
    #   [d2, r21, r22, r23, r24....r242],
    #   ................................
    #   [dm, rm1, rm2, rm3, rm4....rm42] ]
    self.y = [] # one row for each date, length of row is how many strategy returns we predict
    self.y_legend = {} # trader -> index
    self.y_rev_legend = {} # index -> trader

  def LoadIndicatorData(self):
    NUM_INDICATORS = 45

    indicator_date_value = {}
    indicator_last_entry = [None] * (NUM_INDICATORS + 1)
    self.all_dates = []

    for index in range(1, NUM_INDICATORS + 1):
      filename = 'IndicatorData/csvs/eco_indicator_sheet_' + str(index) + '.csv'
      # print('working on ' + filename)

      data = list(open(filename, 'r'))
      # print(str(len(data)))
      date_index, value_index = None, None

      for line in data:
        tokens = line.strip().split(',')
        if len(tokens) >= 2:
          for i in range(0, len(tokens)):
            if tokens[i] == 'Date':
              date_index = i
            if tokens[i] == 'Value':
              value_index = i
        if date_index != None and value_index != None:
          break

      # print(str(date_index) + ' ' + str(value_index))
      for line in data:
        tokens = line.strip().split(',')
        if len(tokens) < max(date_index, value_index) + 1:
          continue

        date, value = tokens[date_index], tokens[value_index]
        if not date or not value or date == 'Date':
          continue

        date = dt.NormalizeDate(date)
        # print(date)

        if date not in self.all_dates:
          self.all_dates.append(date)

        if index not in indicator_date_value:
          indicator_date_value[index] = {}

        indicator_date_value[index][date] = value

    # print(str(len(indicator_date_value.keys())))

    self.all_dates = sorted(self.all_dates,
                            key=functools.cmp_to_key(dt.CompareDates))
    # print(str(all_dates))

    self.indicator_matrix = []
    for date in self.all_dates:
      entry = [date]

      for index in indicator_date_value:
        if date in indicator_date_value[index]:
          indicator_last_entry[index] = indicator_date_value[index][date]

      entry.extend(list(indicator_last_entry))
      self.indicator_matrix.append(entry)

    # print(str(len(indicator_matrix)) + '\n' + str(indicator_matrix[0]) + '\n' + str(indicator_matrix[-1]))

    num_rows = len(self.indicator_matrix)
    num_cols = len(self.indicator_matrix[0])

    # find ratio of actual entry/None in matrix
    cols_to_remove = []
    for index in range(0, num_cols):
      col = list(row[index] for row in self.indicator_matrix)
      num_nones = sum(1 if not x else 0 for x in col)
      ratio = num_nones / num_rows
      if ratio > 0.2:
        cols_to_remove.append(index)

    cols_to_remove.sort(reverse=True)

    print('Removing from indicator data ' + str(cols_to_remove))
    for row in range(0, num_rows):
      for col in cols_to_remove:
        del self.indicator_matrix[row][col]

    num_cols = len(self.indicator_matrix[0])

    for index in range(1, num_cols):
      indicator_value = list(row[index] for row in self.indicator_matrix)
      self.TransformIndicator(indicator_value)
      for row in range(0, len(indicator_value)):
        self.indicator_matrix[row][index] = indicator_value[row]

  def TransformIndicator(self, indicator):
    ma = None
    values = []
    for line in range(0, len(indicator)):
      if not indicator[line]:
        continue

      if not ma:
        ma = float(indicator[line])
        values.append(float(indicator[line]))
        indicator[line] = None
        continue

      values.append(float(indicator[line]))
      indicator[line] = max(-2, min((float(indicator[line]) - ma) / ma, 2))
      ma = statistics.mean(values)
      while len(values) > NUM_DAYS_TO_RECALIBRATE:
        values.pop(0)

  def SetUniformReturns(self, traders):
    for key in traders:
      trader = traders[key]
      pnl = []
      for line in trader.trades:
        date = dt.NormalizeDate(line[0])
        pnl.append([date, line[5]])

      self.trader_pnl_series[trader.Name()] = pnl
      index = len(self.y_legend)

      self.y_legend[trader.Name()] = index
      self.y_rev_legend[index] = trader.Name()

    self.InitializeIndicatorReturnMatrices()

  def InitializeIndicatorReturnMatrices(self):
    # first fill in missing entries in both indicator matrix & trader pnls
    trader_last_index = {}
    trader_last_pnl = {}

    for key in self.y_legend:
      trader_last_index[key], trader_last_pnl[key] = 0, None

    for i, date in enumerate(self.all_dates):
      # insert row for this date
      self.y.append([0] * len(self.y_legend))
      for key in self.y_legend:
        if trader_last_index[key] >= len(self.trader_pnl_series[key]):
          self.y[i][self.y_legend[key]] = trader_last_pnl[key]
          continue

        tdate = self.trader_pnl_series[key][trader_last_index[key]][0]

        if date == tdate:
          pnl = self.trader_pnl_series[key][trader_last_index[key]][1]
          self.y[i][self.y_legend[key]] = pnl
          trader_last_pnl[key] = pnl
          trader_last_index[key] += 1
        else:
          self.y[i][self.y_legend[key]] = trader_last_pnl[key]

      # print(str(i) + '->' + str(date) + '->(' + str(len(self.y[i])) + ')' + str(self.y[i]))

    # for each pnl entry, replace each column with pnl_in_a_month - current_pnl
    for i in range(0, len(self.y)):
      for key in self.y_legend:
        look_ahead = i + NUM_DAYS_TO_RECALIBRATE
        if not self.y[i][self.y_legend[key]] or look_ahead >= len(self.y) or not self.y[look_ahead][self.y_legend[key]]:
          self.y[i][self.y_legend[key]] = None # None-ify other values, so we can ignore them during fitting
          continue

        self.y[i][self.y_legend[key]] = (self.y[look_ahead][self.y_legend[key]] - self.y[i][self.y_legend[key]]) / FIRST_ALLOCATION

      # print(str(i) + '->' + str(self.all_dates[i]) + '->(' + str(len(self.y[i])) + ')' + str(self.y[i]))

    indices_to_remove = []
    for i in range(len(self.all_dates) - 1, -1, -1):
      if not any (self.y[i]):
        del self.y[i]
        del self.all_dates[i]
        del self.indicator_matrix[i]
        indices_to_remove.append(i)
      else:
        self.x.insert(0, self.indicator_matrix[i][1:])

    print('removing index from x, y, indicator_matrix, all_dates: ' + str(len(indices_to_remove)) + ' ' + str(indices_to_remove))
    indices_to_remove = []

    # add previous returns as features for future returns
    starting_index = 0 + NUM_DAYS_TO_RECALIBRATE# need atleast num-days number of past returns to populate row
    for row_i in range(starting_index, len(self.x)):
      # for index 20, look at indices 6 to 19..
      lookback_i = list(range(row_i - NUM_DAYS_TO_RECALIBRATE, row_i))
      # print('appending to indicator matrix row: ' + str(row_i) + ' going to look back on these indices: ' + str(lookback_i))

      for col_i in range(0, len(self.y[0])):
        for look_i in lookback_i:
          self.x[row_i].append(self.y[look_i][col_i])
          # print('appended y[' + str(look_i) + '][' + str(col_i) + '] to x[' + str(row_i) + '][' + str(len(self.x[row_i])) + ']')

    # pop first rows with no returns data
    for i in range(starting_index - 1, -1, -1):
      indices_to_remove.append(i)

    for i in indices_to_remove:
      del self.x[i]
      del self.y[i]
      del self.all_dates[i]
      del self.indicator_matrix[i]

    print('removing index from x, y, indicator_matrix, all_dates: ' + str(len(indices_to_remove)) + ' ' + str(indices_to_remove))

    print('y: ' + str(len(self.y)) + ' x ' + str(len(self.y[0])))
    print('x: ' + str(len(self.x)) + ' x ' + str(len(self.x[0])))
    print('all_dates: ' + str(len(self.all_dates)))

    indices_to_remove = []
    for row in range(len(self.x) - 1, -1, -1):
      if any(l == None for l in self.x[row]):
        indices_to_remove.append(row)
        continue

      if any(l == None for l in self.y[row]):
        indices_to_remove.append(row)

    for i in indices_to_remove:
      del self.x[i]
      del self.y[i]
      del self.all_dates[i]
      del self.indicator_matrix[i]

    print('removing index from x, y, indicator_matrix, all_dates: ' + str(len(indices_to_remove)) + ' ' + str(indices_to_remove))

    print('y: ' + str(len(self.y)) + ' x ' + str(len(self.y[0])))
    print('x: ' + str(len(self.x)) + ' x ' + str(len(self.x[0])))
    print('all_dates: ' + str(len(self.all_dates)))

  def RecalibrateAllocations(self):
    if self.last_date_index >= len(self.all_dates):
      return

    # set index of how much data you're allowed to use to make predictions
    if dt.CompareDates(self.all_dates[self.last_date_index], self.last_date) >= 0:
      return

    while dt.CompareDates(self.all_dates[self.last_date_index], self.last_date) < 0:
      self.last_date_index += 1
      if self.last_date_index >= len(self.all_dates):
        return

    from sklearn import linear_model

    print('fitting ' + str(self.last_date) + ' index: ' + str(self.last_date_index))

    y_preds = [] # projected returns for each strategy
    # train giant model
    for reg in [linear_model.Lasso()]:
      # fit on all data before today
      for col in range(0, len(self.y[0])):
        x = self.x[0:self.last_date_index - 1]
        y = list(row[col] for row in self.y[0:self.last_date_index - 1])

        reg.fit(x, y)

        y_pred = reg.predict([self.x[self.last_date_index]])
        y_preds.append(y_pred[0])

    from sklearn.metrics import explained_variance_score, mean_squared_error, r2_score
    exp_var = explained_variance_score(self.y[self.last_date_index], y_preds)
    mse = mean_squared_error(self.y[self.last_date_index], y_preds)
    r2 = r2_score(self.y[self.last_date_index], y_preds)
    print('prediction_stats: exp_var: ' + str(exp_var) + ' mse: ' + str(mse) + ' r2: ' + str(r2))

    trader_to_allocate = {}
    total_allocation = TOTAL_ALLOCATION
    sum_proj_pnl = 0
    for index in self.y_rev_legend:
      trader = self.y_rev_legend[index]

      if y_preds[index] < 0:
        self.alloc[trader] = MIN_ALLOCATION
        total_allocation -= MIN_ALLOCATION
      else:
        sum_proj_pnl += y_preds[index]
        trader_to_allocate[trader] = y_preds[index]

    for key in trader_to_allocate:
      self.alloc[key] = min(MAX_ALLOCATION, (trader_to_allocate[key] / sum_proj_pnl) * total_allocation)

    print(str(self.last_date) + ' allocs: ' + str(self.alloc))

  def SanityCheckList(self, l):
    import math
    for i in l:
      if i == None or math.isinf(i) or math.isnan(i):
        print(str(i) + ' a problem ' + str(l))
        exit(0)
