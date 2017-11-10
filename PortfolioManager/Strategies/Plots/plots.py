import Strategies.ContractDef.contract_info as ci
import matplotlib.pyplot as plt
import matplotlib.dates as mdt
from datetime import datetime
import math

DPI = 96

def MergeAndPlotTradesAndAlloc(strategy, contract_results, contract_allocs, contracts_db):
  # it would be very hard to have a worse solution than what i'm using here
  # i suck at python :(

  # date to contract to pnl - dict of dicts
  date_contract_pnls, date_contract_allocs = {}, {}

  # list of dates in chrono order
  max_days_key = ('ZC' if 'ZC' in contract_results else list(contract_results.keys())[0])
  date_list = list(trades[0] for trades in list(contract_results[max_days_key]))

  for key in contract_results.keys():
    for i in range(0, len(contract_results[key])):
      trades = contract_results[key][i]
      alloc = contract_allocs[key][i]

      date, pnl = trades[0], trades[5]
      if date not in date_contract_pnls:
        date_contract_pnls[date], date_contract_allocs[date] = {}, {}
      date_contract_pnls[date][key] = pnl
      date_contract_allocs[date][key] = alloc

  # contract to date to pnl - dict of dicts
  contract_date_pnls, contract_date_allocs = {}, {}

  for key in contract_results.keys():
    if key not in contract_date_pnls:
      contract_date_pnls[key], contract_date_allocs[key] = {}, {}
    last_pnl, last_alloc = 0, 0
    for date in date_list:
      # idea is to fill in pnls for days where specific contracts don't have an entry
      last_pnl = (date_contract_pnls[date][key] if key in date_contract_pnls[date] else last_pnl)
      last_alloc = (date_contract_allocs[date][key] if key in date_contract_allocs[date] else last_alloc)
      contract_date_pnls[key][date] = last_pnl
      contract_date_allocs[key][date] = last_alloc

  # date to pnl across all contracts
  date_total_pnls = {}

  for date in date_list:
    date_total_pnls[date] = 0
    for key in contract_results.keys():
      date_total_pnls[date] += contract_date_pnls[key][date]

  pnl_list = list(date_total_pnls[date]/1000.0 for date in date_list)

  fig, axarr = plt.subplots(2, sharex=True)
  fig.tight_layout() # use as much space as you can

  for key in contract_results.keys():
    trades = contract_results[key]
    allocs = contract_allocs[key]
    t_date_list = list(entry[0] for entry in trades)
    dt_objs = []
    for dt in t_date_list:  # create date objects for matlibplot
      dt_objs.append(datetime.strptime(dt, '%m-%d-%y'))
    dates = mdt.date2num (dt_objs)

    pnl = []
    last_pnl = 0
    for entry in trades:
      try:
        # pnl.append(math.log10(entry[5]/1000.0))
        pnl.append((entry[5]/1000.0))
      except ValueError:
        pnl.append(last_pnl)
      last_pnl = pnl[-1]

    alloc = list(entry/1000.0 for entry in allocs)

    axarr[0].plot_date(dates, pnl, linestyle='solid', linewidth=0.5, markersize=0.5, label='pnl-log$Ks-' + key)
    axarr[1].plot_date(dates, alloc, linestyle='solid', linewidth=0.5, markersize=0.5, label='alloc-$Ks' + key)

  axarr[0].set_title(strategy + ' - strategy pnls')
  axarr[0].legend(loc='upper left', fontsize=4, title=strategy)
  axarr[1].set_title(strategy + ' - strategy allocations')
  axarr[1].legend(loc='upper left', fontsize=4, title=strategy)
  axarr[1].axhline(y=0, color='black', linestyle='-')

  all_dt_objs = []
  for dt in date_list: # create date objects for matlibplot
    all_dt_objs.append(datetime.strptime(dt, '%m-%d-%y'))
  all_dates = mdt.date2num(all_dt_objs)

  total_pnl = pnl_list[-1]
  # print('\t', strategy, 'STATS', 'total-pnl($ billions):', total_pnl/1000000.0)

  plt.xlabel('date')
  plt.savefig(strategy + '.png', bbox_inches='tight', dpi=DPI*5)
  mng = plt.get_current_fig_manager()
  mng.full_screen_toggle()
  plt.show()
  plt.close('all') # free memory

  return all_dates, pnl_list

def ComparePlots(all_dates, pm_pnl_list):
  for pm in pm_pnl_list:
    pnl_list = list(pnl/1000.0 for pnl in pm_pnl_list[pm])
    plt.plot_date(all_dates, pnl_list, linestyle='solid', label=str(pm) + '-total-pnl-$millions')

  plt.legend (loc='upper left')
  plt.xlabel('date')
  plt.savefig('PMComparePlots.png', bbox_inches='tight', dpi=DPI*5)
  mng = plt.get_current_fig_manager()
  mng.full_screen_toggle()
  plt.show()
  plt.close('all') # free memory

def PlotEfficientFrontierPlot(std_mean):
  for line in std_mean:
    print('adding ' + str(line))
    plt.plot(line[0], line[1], 'o', label=line[2])

  plt.legend(loc='lower right')
  plt.xlabel('stdev')
  plt.ylabel('avg-pnl')
  plt.savefig('EfficientFrontier.png', bbox_inches='tight', dpi=DPI*5)
  mng = plt.get_current_fig_manager()
  mng.full_screen_toggle()
  plt.show()
  plt.close('all')

def PlotList(l, title):
  plt.xlabel('points')
  plt.ylabel(title)
  plt.scatter(range(0, len(l)), l)
  plt.title(title)
  plt.savefig(title + '.png', bbox_inches='tight', dpi=DPI)
  mng = plt.get_current_fig_manager()
  mng.full_screen_toggle()
  # plt.show()
  plt.close('all')

def PlotXY(x, y, title):
  plt.xlabel('x')
  plt.ylabel('y')
  plt.scatter(x, y)
  plt.title(title)
  plt.savefig(title + '.png', bbox_inches='tight', dpi=DPI)
  mng = plt.get_current_fig_manager()
  mng.full_screen_toggle()
  # plt.show()
  plt.close('all')
