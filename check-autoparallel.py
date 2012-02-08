import csv
import collections
import math
from pprint import pprint

def iterCsvRecords(path, className):
    with open(path, 'rb') as f:
        reader = csv.reader(f)
        clazz = None
        for row in reader:
            if clazz is None:
                clazz = collections.namedtuple(className, row)
            else:
                yield clazz(*row)

benchTable = collections.defaultdict(dict)
for brec in iterCsvRecords('benchmarks.txt', 'BenchmarkRecord'):
    benchTable[brec.testID][brec.benchName] = brec

def geomAverage(values):
    averageExp = sum([math.log(x) for x in values]) / len(values)
    return math.exp(averageExp)

for benchType in ['INT', 'FP']:
    print 'Top contributing benchmarks to %s results, by maximum multiple of the geometric average:' % benchType
    topBenchResults = {}
    summaryTable = {}
    for srec in iterCsvRecords('summaries.txt', 'SummaryRecord'):
        summaryTable[srec.testID] = srec
        if srec.autoParallel == 'Yes' and benchType in srec.benchType:
            base = geomAverage([float(brec.base) for brec in benchTable[srec.testID].itervalues()])
            for brec in benchTable[srec.testID].itervalues():
                r = (float(brec.base) / base, brec)
                topBenchResults[brec.benchName] = max(r, topBenchResults.get(brec.benchName, (0, None)))
    for v, k in sorted([(v, k) for k, v in topBenchResults.iteritems()], reverse=True):
        benchValue, brec = v
        print benchValue, k, brec.testID, summaryTable[brec.testID].machine
    print
        

