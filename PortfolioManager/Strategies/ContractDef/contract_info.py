class ContractInfo:
  def __init__(self, name, min_price_increment, tick_value):
    self.name = name
    self.min_price_increment = min_price_increment
    self.tick_value = tick_value

  @property
  def Name(self):
    return self.name

  @Name.setter
  def Name(self, value):
    self.name = value

  @property
  def MinPriceIncrement(self):
    return self.min_price_increment

  @property
  def TickValue(self):
    return self.tick_value

  def ToString(self):
    print('[name:', self.Name,
          'min-increment:', self.MinPriceIncrement,
          'tick-value:', self.TickValue,
          ']',sep='|')

# Have a db with instrument specific information
ContractInfoDatabase = {
                        # equities
                        'ES':ContractInfo('ES', 0.25, 12.5),
                        'NQ':ContractInfo('NQ', 0.25, 5.0),
                        # energies
                        'CL':ContractInfo('CL', 0.01, 10.0),
                        'HO':ContractInfo('HO', 0.01, 4.2),
                        # fx
                        '6E':ContractInfo('6E', 0.00005, 6.25),
                        '6B':ContractInfo('6B', 0.01, 6.25),
                        # treasury
                        'ZN':ContractInfo('ZN', 0.015625, 15.625),
                        'ZB':ContractInfo('ZB', 0.031250, 31.250),
                        # metals
                        'SI':ContractInfo('SI', 0.005, 25),
                        'GC':ContractInfo('GC', 0.1, 10),
                        # commodities
                        'ZC':ContractInfo('ZC', 0.25, 12.5),
                        'ZW':ContractInfo('ZW', 0.25, 12.5)
                      }
