import Strategies.ContractDef.contract_info as ci

# function to deal with eberhart csv files
# tokenize, check sanity, convert prices to ticks
def TokenizeToPriceInfo(contract, line):
  tokens = line.strip().split(',')
  ticks_tokens = []

  # expecting:
  # Date, Open, High, Low, Close
  if len(tokens) != 5:
    print('ERROR ignoring malformed line ', line.strip())
    return ticks_tokens

  for entry in tokens:
    if entry.upper() == 'DATE':
      break

    try:
      ticks_tokens.append(float(entry)/contract.MinPriceIncrement)
    except ValueError:
      # this case is for treasuries where prices are quoted in 1/32nds
      if entry.count('-') == 1:
        try_tokens = entry.split('-')
        new_price = (float(try_tokens[0]) + float(try_tokens[1])/32)
        ticks_tokens.append (new_price/contract.MinPriceIncrement)
      else:
        ticks_tokens.append(entry)

  return ticks_tokens

# pull date from a market data line
def TokenizeToDate(contract, line):
  try:
    # unpack list
    date, *rem =\
      TokenizeToPriceInfo(contract, line)
    return date
  except ValueError or TypeError:
    pass

  return None
