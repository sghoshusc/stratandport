from datetime import datetime

# deal with 2 different year formats
def NormalizeDate(d):
  if not d or len(d) < 10:
    return d

  tokens = d.split('-')
  d = tokens[1] + '-' + tokens[2] + '-' + tokens[0][-2:]
  return d

# return < 0 if d1 < d2
# return > 0 if d1 > d2
# return = 0 if d1 = d2
def CompareDates(d1, d2):
  if not d1 or not d2:
    return 0

  # 1953-04-01 => yyyy-mm-dd
  #   08-15-17 => mm-dd-yy
  dt1 = datetime.strptime(d1, '%m-%d-%y') if len(d1) < 10 else datetime.strptime(d1, '%Y-%m-%d')
  dt2 = datetime.strptime(d2, '%m-%d-%y') if len(d2) < 10 else datetime.strptime(d2, '%Y-%m-%d')

  if dt1 < dt2:
    return -1
  if dt1 > dt2:
    return 1

  return 0

# return days between 2 days
def NumDaysBetween(d1, d2):
  dt1 = datetime.strptime(d1, '%m-%d-%y')
  dt2 = datetime.strptime(d2, '%m-%d-%y')

  return abs((dt1 - dt2).days) - 8
