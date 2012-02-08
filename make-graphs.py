import csv
import collections
import datetime
import math
import re
import itertools
import sys
import urllib2
import os
from contextlib import contextmanager

try:
    import cairo
    try:
        import PIL.Image
    except:
        sys.stderr.write('PIL not installed. HQ antialiasing is disabled.\n')
except:
    sys.stderr.write('Pycairo not installed. Writing .txt files only.\n')


#---------------------------------------------------------
#  Helper functions
#---------------------------------------------------------

def geometricAverage(values):
    if len(values) == 0:
        return 1
    prod = reduce(lambda x, y: x * y, values)
    return prod ** (1.0 / len(values))
    
def isWithinPercent(a, b, percent):
    if a > b:
        a, b = b, a     # Make sure a is the smaller one
    return b < a * (1 + percent / 100.0)

def monthDelta(loDate, hiDate):
    return (hiDate.year * 12 + hiDate.month) - (loDate.year * 12 - loDate.month)

@contextmanager
def redirected_to_file(path):
    save_stdout = sys.stdout
    sys.stdout = open(path, 'w')
    try:
        yield None
    finally:
        sys.stdout = save_stdout
        
@contextmanager
def saved(cr):
    cr.save()
    try:
        yield cr
    finally:
        cr.restore()


#---------------------------------------------------------
#  Determine CPU family & speed from name
#---------------------------------------------------------

def extractMHzFromName(name):
    m = re.search('(\\d+(?:\\.\\d+)?)a? ?([mg]hz)', name.lower())
    value, units = m.groups()
    value = float(value)
    if units == 'ghz':
        value *= 1000
    return value
    
def identifyCPU(r):
    # Remove cruft
    cpu = r.cpu
    for cruft in ['(TM)', '(R)', 'processor', 'Processor', '\xae', '\x99',
                  'supporting Hyper-Threading Technology',
                  'with Hyper-Threading Technology',
                  'with HT Technology',
                  'dual-core',
                  'Dual-Core',
                  'Quad-Core',
                  'Dual Core',
                  'Single Chip',
                  'w/ MMX technology',
                  'with MMX technology',
                  'with 2MB L2 Cache',
                  '64-bit',
                  'Model']:
        cpu = cpu.replace(cruft, ' ')
    cpu = re.sub('\\([^)]*\\)', ' ', cpu)
    cpu = re.sub('/?\\d+(?:\\.\\d+)?[Aa]? ?[mMgG][hH][zZ]', ' ', cpu)
    cpu = cpu.split(',')[0]
    cpu = ' '.join(cpu.split())

    # Identify brand and model
    xeon = ' Xeon' if 'xeon' in cpu.lower() else ''
    if 'Pentium III' in cpu or 'PentiumIII' in cpu:
        return 'Intel Pentium', 'Pentium III' + xeon
    if 'Pentium II' in cpu:
        return 'Intel Pentium', 'Pentium II' + xeon
    if xeon:
        m = re.search('E7-[^\\s]+', cpu)
        if m:
            return 'Intel Xeon', 'Xeon ' + m.group()
        m = re.search('E3-[^\\s]+', cpu)
        if m:
            return 'Intel Xeon', 'Xeon ' + m.group()
        m = re.search('[A-Z]?(\\d)\\d{3}[A-Z]?', cpu)
        if m:
            return 'Intel Xeon', 'Xeon ' + m.group()
        if cpu == 'Intel Xeon MP':
            return 'Intel Xeon', 'Xeon MP'
        if cpu in ['Intel Xeon', 'Xeon']:
            return 'Intel Xeon', 'Xeon (unspecified model)'
        if re.match('Intel Xeon (\\d\\.\\d|2M Cache)(Hz)?', cpu):
            return 'Intel Xeon', 'Xeon (unspecified model)'
        if cpu.startswith('Intel Xeon LV'):
            return 'Intel Xeon', 'Xeon LV'
        if cpu.startswith('Intel LV Xeon 400'):
            return 'Intel Xeon', 'Xeon LV'
    if cpu.startswith('Intel Core i'):
        return 'Intel Core', cpu[6:]
    if cpu.startswith('Intel Core 2 '):
        return 'Intel Core', cpu[6:]
    if cpu.startswith('Intel Core2 '):
        return 'Intel Core', 'Core 2 ' + cpu[12:]
    if cpu.startswith('Intel Core '):
        return 'Intel Core', cpu[6:]
    if cpu.startswith('Intel Pentium D'):
        return 'Intel Pentium', cpu[6:]
    if re.match('R1\\d000', cpu):
        return 'MIPS', cpu
    if re.match('MIPS R1\\d000', cpu):
        return 'MIPS', cpu[5:11]
    i = cpu.find('Pentium 4')
    if i >= 0:
        return 'Intel Pentium', cpu[i:]
    if cpu == 'Intel P4':
        return 'Intel Pentium', 'Pentium 4'
    if cpu == 'Pentium':
        return 'Intel Pentium', 'Pentium'
    if cpu in ['Pentium Pro', 'Pentium-Pro']:
        return 'Intel Pentium', 'Pentium Pro'
    if cpu.startswith('Intel Pentium'):
        m = re.match('Intel Pentium ((?:M )?[A-Z]?\\d{3,4}T?)', cpu)
        if m:
            return 'Intel Pentium', 'Pentium ' + m.group(1)
        return 'Intel Pentium', cpu[6:]
    if cpu == 'Celeron':
        return 'Intel Celeron', 'Celeron'
    if cpu.startswith('Intel Celeron'):
        return 'Intel Celeron', cpu[6:]
    m = re.search('21\\d64[A-Z]*', cpu)
    if m:
        return 'DEC Alpha', 'Alpha ' + m.group()    
    if cpu.startswith('POWER'):
        return 'IBM POWER', cpu
    m = re.search('PowerPC.*', cpu)
    if m:
        return 'PowerPC', m.group()
    if cpu in ['RS64 IV', 'RS64 II']:
        return 'PowerPC', cpu
    if cpu.startswith('Power'):
        return 'IBM POWER', cpu.upper()
    if cpu.startswith('IBM Power'):
        return 'IBM POWER', cpu.upper()[4:]
    if cpu.startswith('P2SC'):
        return 'IBM POWER', 'P2SC'
    if cpu.startswith('MIPS'):
        return 'MIPS', cpu.split()[1]
    if re.match('(100 )?R\\d{4}', cpu):
        return 'MIPS', cpu
    if cpu.startswith('SPARC64'):
        return 'Fujitsu SPARC', cpu
    if cpu.startswith('MicroSPARC'):
        return 'Sun SPARC', cpu
    if cpu.startswith('UltraSPARC'):
        return 'Sun SPARC', cpu
    if cpu.startswith('SuperSPARC'):
        return 'Sun SPARC', cpu
    if cpu == 'SPARC T3':
        return 'Sun SPARC', cpu
    if cpu == 'TurboSPARC':
        return 'Fujitsu SPARC', 'TurboSPARC'
    if cpu in ['512k HyperCACHE', 'HyperSPARC']:
        return 'Fujitsu SPARC', 'HyperSPARC'
    if cpu == 'ULV Intel Pentium M':
        return 'Intel Pentium', 'Pentium M'
    if cpu.startswith('AMD FX-'):
        return 'AMD FX', cpu[4:]
    if cpu.startswith('AMD'):
        name = cpu.split()
        return 'AMD ' + name[1], ' '.join(name[1:])
    if cpu.startswith('Opteron'):
        return 'AMD Opteron', cpu
    i = cpu.find('Itanium')
    if i >= 0:
        name = cpu[i:]
        name = name.replace('Itanium2', 'Itanium 2')
        name = name.replace(' FSB', '')
        return 'Intel Itanium', name
    if cpu.startswith('PA-'):
        cpu = cpu.replace('PA-RISC ', 'PA-')
        cpu = cpu.replace('_', '')
        return 'HP PA-RISC', cpu
    if cpu == 'PA8600':
        return 'HP PA-RISC', 'PA-8600'
    if 'Xeon' in r.cpu:
        return 'Intel Xeon', 'Xeon (unspecified model)'
    if r.srec.machine == 'AlphaServer 2100A 5/300':
        return 'DEC Alpha', 'Alpha 21164'
    return '???', cpu
   

#---------------------------------------------------------
#  Iterate through CPU95, CPU2000, CPU2006 .csv files
#---------------------------------------------------------

Result = collections.namedtuple('Result', 'benchType cpu mhz hwDate score srec benches')

DISQUALIFIED_BENCHMARKS = [
    '483.xalancbmk',
    '445.gobmk',
    '456.hmmer',
    '464.h264ref',
    '429.mcf',
    '462.libquantum'
    '434.zeusmp',
    '459.GemsFDTD',
    '437.leslie3d',
    '436.cactusADM',
    '470.lbm',
    '410.bwaves',
]

def iterCsvRecords(path, className):
    with open(path, 'rb') as f:
        reader = csv.reader(f)
        clazz = None
        for row in reader:
            if clazz is None:
                clazz = collections.namedtuple(className, row)
            else:
                yield clazz(*row)

def iterResults():
    benchTable = collections.defaultdict(dict)
    for brec in iterCsvRecords('benchmarks.txt', 'BenchmarkRecord'):
        benchTable[brec.testID][brec.benchName] = brec
    summaryTable = {}
    for srec in iterCsvRecords('summaries.txt', 'SummaryRecord'):
        summaryTable[srec.testID] = srec
        benches = [brec for brec in benchTable[srec.testID].itervalues()
                   if brec.benchName not in DISQUALIFIED_BENCHMARKS]
        hwDate = datetime.datetime.strptime(srec.hwAvail, '%b-%Y')
        yield Result(benchType=srec.benchType,
                     cpu=srec.cpu,
                     mhz=float(srec.mhz),
                     hwDate=hwDate,
                     score=geometricAverage([float(brec.base) for brec in benches]),
                     srec=srec,
                     benches=benches)


#---------------------------------------------------------
#  Uniquely identify CPUs
#---------------------------------------------------------

CPUInfo = collections.namedtuple('CPUInfo', 'brand model mhz')

class CPUDatabase:
    def __init__(self):
        self.modelSpeeds = collections.defaultdict(list)

    def identify(self, r):
        brand, model = identifyCPU(r)
        speeds = self.modelSpeeds[brand, model]
        for other in speeds:
            # if mhz is within 5% of an existing cpu, return that one
            if isWithinPercent(r.mhz, other.mhz, 5):
                return other
        cpu = CPUInfo(brand, model, r.mhz)
        speeds.append(cpu)
        return cpu

CPUDB = CPUDatabase()


#---------------------------------------------------------
#  Graph rendering
#---------------------------------------------------------

if 'PIL' in globals():
    class HQSurface:
        def __init__(self, width, height, zooms=2):
            self.width, self.height = width, height
            self.zooms = zooms
            self.surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width * 2**zooms, height * 2**zooms)
            cr = self.cr = cairo.Context(self.surface)
            if zooms > 0:
                cr.scale(2.0, 2.0)
                cr.translate(0.5, 0.5)
            for i in xrange(1, zooms):
                cr.scale(2.0, 2.0)
                
        def write_to_png(self, path):
            im = PIL.Image.frombuffer('RGBA', (self.surface.get_width(), self.surface.get_height()), self.surface.get_data(), 'raw', 'BGRA', 0, 1)
            for i in xrange(self.zooms - 1, -1, -1):
                im = im.resize((self.width * 2**i, self.height * 2**i), PIL.Image.BILINEAR)
            im.save(path)
            
DEFAULT_FONT_OPTIONS = cairo.FontOptions()
DEFAULT_FONT_OPTIONS.set_antialias(cairo.ANTIALIAS_SUBPIXEL)

def createScaledFont(family, size, slant=cairo.FONT_SLANT_NORMAL, weight=cairo.FONT_WEIGHT_NORMAL):
    face = cairo.ToyFontFace(family, slant, weight)
    return cairo.ScaledFont(face, cairo.Matrix(xx=size, yy=size), cairo.Matrix(), DEFAULT_FONT_OPTIONS)

def alignText(cr, scaledFont, align, text, x, y):
    x_bearing, y_bearing, width, height = scaledFont.text_extents(text)[:4]
    with saved(cr):
        cr.set_font_options(DEFAULT_FONT_OPTIONS)
        cr.set_scaled_font(scaledFont)
        cr.move_to(x - width * align - x_bearing, y)
        cr.show_text(text)
    
ResultInBrand = collections.namedtuple('ResultInBrand', 'hwDate convertedScore cpu result')

def RenderGraph(mode, resultsByBrand, outPath):
    # If 1 pixel travels M months horizontally,
    # it should travel M*pixelAspect logScore points vertically,
    # and we fix the whole thing inside maxGraphSize.
    maxGraphSize = (580.0, 380.0)
    pixelAspect = 0.06   
    minLogScore = -3
    minDate = datetime.datetime(1995, 1, 1)

    # Calculate axis extents and actual graph size.
    allRibs = sum(resultsByBrand.values(), [])
    maxDate = max([r.hwDate for r in allRibs])
    months = monthDelta(minDate, maxDate)
    maxLogScore = int(round(math.log(max([r.convertedScore for r in allRibs]), 2)))
    logScoreRange = maxLogScore - minLogScore
    pelsPerMonth = min(maxGraphSize[0] / months,
                       maxGraphSize[1] / logScoreRange * pixelAspect)
    graphSize = (months * pelsPerMonth, logScoreRange * pelsPerMonth / pixelAspect)
    
    # Different shapes that are used on the graph.
    def circle(cr, x, y):
        cr.arc(x, y, 2.5, 0, 2*math.pi)

    def triangle(cr, x, y):
        x, y = round(x)+.5, round(y)
        cr.move_to(x-3, y+3)
        cr.line_to(x, y-3)
        cr.line_to(x+3, y+3)
        cr.close_path()

    def square(cr, x, y):
        x, y = round(x), round(y)
        cr.rectangle(x-2, y-2, 5, 5)
        
    # Brands will be rendered in this order, as separate layers.
    # That way, we can hide the busiest brands (like Xeon) at the bottom.
    brandColors = [
        ('003471', 'Intel Xeon', square, 0),
        ('0072bc', 'Intel Core', circle, 1),
        ('ffa080', 'DEC Alpha', circle, 13),
        ('007236', 'AMD Opteron', square, 6),
        ('86dce3', 'Intel Pentium', circle, 2),
        ('a0d49b', 'AMD Phenom', triangle, 7),
        ('31d100', 'AMD Athlon', circle, 8),
        ('377dfc', 'Intel Itanium', triangle, 3),
        ('fdad4f', 'Fujitsu SPARC', triangle, 11),
        ('f8e400', 'Sun SPARC', circle, 12),
        ('c1d72f', 'AMD FX', square, 5),
        ('d59d55', 'MIPS', square, 14),
        ('03d3ff', 'Intel Celeron', square, 4),
        ('f198dd', 'IBM POWER', triangle, 9),
        ('e040de', 'PowerPC', circle, 10),
        ('947b30', 'HP PA-RISC', circle, 15),
    ]
    recognized = set([b[1] for b in brandColors])

    # Create surface and context.
    w, h = int(graphSize[0] + 40), int(graphSize[1] + 75)
    if 'PIL' in globals():
        surface = HQSurface(w, h)
        cr = surface.cr
    else:
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        cr = cairo.Context(surface)
    cr.set_line_width(1)
    cr.translate(28, 37)
    cr.set_source_rgb(1, 1, 1)
    cr.paint()    

    # Title.
    mode = mode.lower()
    fullType = { 'fp': 'Floating-Point', 'int': 'Integer' }[mode]
    with saved(cr):
        titleFont = createScaledFont('Arial', 20, weight=cairo.FONT_WEIGHT_BOLD)
        cr.set_source_rgb(0, 0, 0)
        alignText(cr, titleFont, .5, 'Single-Threaded %s Performance' % fullType, graphSize[0] / 2 - 10, -19)
        subTitleFont = createScaledFont('Arial', 11)
        cr.set_source_rgb(.6, .6, .6)
        alignText(cr, subTitleFont, .5, u'Based on adjusted SPEC%s\xae results' % mode, graphSize[0] / 2, -5)
    
    # Shaded area.
    with saved(cr):
        x = round(12 * 9 * pelsPerMonth)
        cr.set_source_rgb(.98, .98, .98)
        cr.rectangle(x, 0, round(graphSize[0]) - x, round(graphSize[1]))
        cr.fill()
        
    # Render grid lines.
    with saved(cr):
        scoreFont = createScaledFont('Arial', 14)
        fractionFont = createScaledFont('Arial', 16)
        cr.set_source_rgb(.9, .9, .9)
        # Horizontal
        for rls in range(maxLogScore - minLogScore + 1):
            y = round(graphSize[1] - rls * pelsPerMonth / pixelAspect)
            with saved(cr):
                cr.set_source_rgb(.6, .6, .6)
                exp = minLogScore + rls
                if exp >= 0:
                    label = str(2 ** exp)
                    f = scoreFont
                else:
                    label = { -1: unichr(189), -2: unichr(188) }.get(exp, '')
                    f = fractionFont
                alignText(cr, f, 1, label, -6, y + 6)
            cr.move_to(0, y + .5)
            cr.rel_line_to(graphSize[0], 0)
            cr.stroke()
        # Vertical
        assert minDate.month == 1
        for month in range(0, months, 12):
            x = round(month * pelsPerMonth)
            cr.move_to(x + .5, 0)
            cr.rel_line_to(0, graphSize[1])
            cr.stroke()
        cr.move_to(round(months * pelsPerMonth) + .5, 0)
        cr.rel_line_to(0, graphSize[1])
        cr.stroke()
        yearFont = createScaledFont('Arial', 13)
        for month in range(6, months, 12):
            x = month * pelsPerMonth
            with saved(cr):
                cr.set_source_rgb(.6, .6, .6)
                cr.translate(x, graphSize[1])
                cr.rotate(-math.pi / 4)
                alignText(cr, yearFont, 1, str(minDate.year + month / 12), -4, 12)

    # Render each brand as another layer.
    totalPoints = 0
    with saved(cr):
        for color, brand, shape, listOrder in [('808080', None, circle, -1)] + sorted(brandColors):
            if brand:
                rib = resultsByBrand[brand]
            else:
                rib = sum([rib for b, rib in resultsByBrand.iteritems() if b not in recognized], [])
            cr.set_source_rgb(*[int(color[i:i+2], 16)/255.0 for i in xrange(0, 6, 2)])
            for r in rib:
                logScore = math.log(r.convertedScore, 2)
                x = (monthDelta(minDate, r.hwDate) - .5) * pelsPerMonth
                y = (logScore - minLogScore) * pelsPerMonth / pixelAspect
                if x >= 0 and y >= 0:
                    totalPoints += 1
                    shape(cr, x, graphSize[1] - y)
                    cr.fill()
    print '%d points plotted for SPEC%s' % (totalPoints, mode)
    
    # Render legend.
    with saved(cr):
        legendFont = createScaledFont('Arial', 11)
        spacing = 11
        w, h = 90, spacing * len(brandColors) + 4
        cr.translate(int(graphSize[0]) - w - 23, int(graphSize[1]) - h - 23)
        cr.set_source_rgb(1, 1, .98)
        cr.rectangle(0, 0, w, h)
        cr.fill()
        cr.set_source_rgb(.7, .7, .7)
        cr.rectangle(.5, .5, w, h)
        cr.stroke()
        cr.translate(7, 9)
        for color, brand, shape, listOrder in brandColors:
            # Icon
            cr.set_source_rgb(*[int(color[i:i+2], 16)/255.0 for i in xrange(0, 6, 2)])
            shape(cr, 0, listOrder * spacing - 1)
            cr.fill()
            # Text
            cr.set_source_rgb(0, 0, 0)
            alignText(cr, legendFont, 0, brand, 6, listOrder * spacing + 3)
    
    surface.write_to_png(outPath)


#---------------------------------------------------------
#  Main
#---------------------------------------------------------

ALL_RESULTS = list(iterResults())
for r in ALL_RESULTS:
    CPUDB.identify(r)

# Dump table of identified CPU names.
# Good for tweaking identifyCPU.
with redirected_to_file('identified_cpus.txt'):
    # Number of CPUs in each brand:
    brand = None
    for k, speeds in sorted(CPUDB.modelSpeeds.items()) + [((None, ''), [])]:
        if brand != k[0]:
            if brand is not None:
                print '%s x %d' % (brand, count)
            brand = k[0]
            count = 0
        count += 1
    print

    # Individual models:
    table = dict([(r.cpu, r) for r in ALL_RESULTS])
    for dummy, r in sorted(table.items()):
        cpu = CPUDB.identify(r)
        id = '%s|%s (%d Mhz)' % (cpu.brand, cpu.model, r.mhz)
        print '%-60s "%s" %s#%s' % (id, r.cpu, r.benchType, r.srec.testID)
        print '%-60s "%s" %s#%s' % (id, r.cpu, r.benchType, r.srec.testID)

# Scan INT benchmarks, then FP.
for MODE in ['INT', 'FP']:
    benchTypes = [t % MODE for t in ['C%s95', 'C%s2000', 'C%s2006']]
    
    # resultsByCPU: Maps CPUInfo to a list of results using that cpu.
    resultsByCPU = collections.defaultdict(list)

    # Iterate through all results.
    for r in ALL_RESULTS:
        if r.benchType in benchTypes:
            cpu = CPUDB.identify(r)
            resultsByCPU[cpu].append(r)

    # Find conversion ratios by taking the geometric average of all
    # available conversion ratios.
    ratio2000 = []
    ratio2006 = []
    for cpu, results in resultsByCPU.iteritems():
        sliceByType = [[r.score for r in results if r.benchType == b] for b in benchTypes]
        if sliceByType[0] and sliceByType[1]:
            # We have a 2000/95 conversion ratio for this CPU.
            ratio2000.append(geometricAverage(sliceByType[1]) / geometricAverage(sliceByType[0]))
        if sliceByType[1] and sliceByType[2]:
            # We have a 2006/2000 conversion ratio for this CPU.
            ratio2006.append(geometricAverage(sliceByType[2]) / geometricAverage(sliceByType[1]))
    ratio2000 = geometricAverage(ratio2000)
    ratio2006 = geometricAverage(ratio2006)
    conversionRatios = [ratio2000 * ratio2006, ratio2006, 1]

    # Group results by brand, convert scores and sort.
    resultsByBrand = collections.defaultdict(list)
    for cpu, results in resultsByCPU.iteritems():
        for r in results:
            convertedScore = r.score * conversionRatios[benchTypes.index(r.benchType)]
            resultsByBrand[cpu.brand].append(ResultInBrand(r.hwDate, convertedScore, cpu, r))
    for rib in resultsByBrand.itervalues():
        rib.sort()

    # Dump results file.                                             
    with redirected_to_file('%s_report.txt' % MODE.lower()):
        print '%s = %f x %s' % (benchTypes[1], ratio2000, benchTypes[0])
        print '%s = %f x %s' % (benchTypes[2], ratio2006, benchTypes[1])
        print
        for brand, rib in sorted(resultsByBrand.items()):
            print
            print
            print brand
            print '=' * len(brand)
            for hwDate, convertedScore, cpu, result in rib:
                print '    %s: %f by "%s" %d MHz (%s=%.1f, %s) %s' % (
                    hwDate.strftime('%Y-%b'),
                    convertedScore,
                    cpu.model,
                    cpu.mhz,
                    result.benchType,
                    result.score,
                    result.srec.testID,
                    ', '.join([brec.base for brec in result.benches]))

    # Render the graph.
    if 'cairo' in globals():
        RenderGraph(MODE, resultsByBrand, '%s_graph.png' % MODE.lower())
