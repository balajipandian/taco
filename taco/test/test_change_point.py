'''
TACO: Transcriptome meta-assembly from RNA-Seq
'''
import os
import numpy as np
import h5py
import matplotlib.pyplot as plt

from taco.lib.base import Strand, Exon
from taco.lib.dtypes import FLOAT_DTYPE
from taco.lib.splice_graph import SpliceGraph, SGNode
from taco.lib.cchangepoint import mse as mse_cython
from taco.lib.changepoint import mse as mse_python, smooth, run_changepoint
from taco.lib.assemble import assemble_isoforms, Config
from taco.lib.transfrag import Transfrag

from taco.test.base import read_single_locus


def test_mse():
    a = np.zeros(100, dtype=FLOAT_DTYPE)
    a[:50] = 10
    a[50:] = 0
    a += np.random.random(100)
    mse_min_c, mse_i_c = mse_cython(a)
    mse_min_py, mse_i_py = mse_python(a)
    assert mse_i_c == 50
    assert mse_i_c == mse_i_py
    assert np.allclose(mse_min_c, mse_min_py, atol=0.01)
    return


def test_trim_transfrags():

    def make_ramp(strand, sign=1):
        transfrags = []
        chrom = 'chr1'
        start = 1000
        end = 1220
        change_expr = 0.0
        base_expr = 0.0
        # "flat" part of expression landscape
        expr = 1.0
        for i in xrange(0, 50):
            t = Transfrag(chrom=chrom, strand=strand,
                          _id='T1.%d' % i, sample_id='S%d' % i,
                          expr=expr, is_ref=False,
                          exons=[Exon(start, end)])
            transfrags.append(t)
            change_expr += expr
            base_expr += expr
        # "changing" area
        i = 0
        expr = 10.0
        for pos in range(1100, 1120):
            left, right = (start, pos) if sign < 0 else (pos, end)
            t = Transfrag(chrom=chrom, strand=strand,
                          _id='T2.%d' % i, sample_id='S%d' % i,
                          expr=expr, is_ref=False,
                          exons=[Exon(left, right)])
            transfrags.append(t)
            change_expr += expr
            i += 1
        return chrom, start, end, strand, change_expr, base_expr, transfrags

    # positive strand
    tup = make_ramp(Strand.POS, sign=-1)
    chrom, start, end, strand, change_expr, base_expr, transfrags = tup
    sgraph = SpliceGraph.create(transfrags)
    cps = run_changepoint(sgraph.expr_data, smooth_window_len=11)
    assert len(cps) == 1
    cp = cps[0]
    assert cp.pos == 110
    assert cp.foldchange < 0.5
    assert cp.sign == -1
    cp = cp._replace(pos=start + cp.pos,
                     start=start + cp.start,
                     end=start + cp.end)
    # trim transfrags
    sgraph._trim_change_point(cp)
    expr_data_after = sgraph._compute_expression()
    assert expr_data_after[0] == 250
    assert expr_data_after[-1] == 50
    assert expr_data_after[cp.index - 1] == 150
    assert expr_data_after[cp.index] == base_expr

    # now try SpliceGraph interface
    tup = make_ramp(Strand.POS, sign=-1)
    chrom, start, end, strand, change_expr, base_expr, transfrags = tup
    sgraph = SpliceGraph.create(transfrags)
    cps = sgraph.detect_change_points(smooth_window_len=11)
    for cp in cps:
        sgraph.apply_change_point(cp)
    sgraph.recreate()
    assert sgraph.expr_data[cp.index - 1] == 150
    assert sgraph.expr_data[cp.index] == base_expr
    assert cp.pos in sgraph.stop_sites

    # negative strand should not affect change point
    tup = make_ramp(Strand.NEG, sign=-1)
    chrom, start, end, strand, left_expr, base_expr, transfrags = tup
    sgraph = SpliceGraph.create(transfrags)
    cps = sgraph.detect_change_points(smooth_window_len=11)
    for cp in cps:
        sgraph.apply_change_point(cp)
    sgraph.recreate()
    assert sgraph.expr_data[cp.index - 1] == 150
    assert sgraph.expr_data[cp.index] == base_expr
    assert cp.pos in sgraph.start_sites

    # neg strand change in opposite direction
    tup = make_ramp(Strand.NEG, sign=1)
    chrom, start, end, strand, left_expr, base_expr, transfrags = tup
    sgraph = SpliceGraph.create(transfrags)
    cps = run_changepoint(sgraph.expr_data, smooth_window_len=11)
    cp = cps[0]
    assert cp.index == 110
    assert cp.foldchange < 0.5
    assert cp.sign == 1.0
    cps = sgraph.detect_change_points(smooth_window_len=11)
    cp = cps[0]
    for cp in cps:
        sgraph.apply_change_point(cp)
    sgraph.recreate()
    assert sgraph.expr_data[0] == 50
    assert sgraph.expr_data[-1] == 250
    assert sgraph.expr_data[cp.index - 1] == base_expr
    assert sgraph.expr_data[cp.index] == 160
    assert cp.pos in sgraph.stop_sites

    # pos strand change in opposite direction
    tup = make_ramp(Strand.POS, sign=1)
    chrom, start, end, strand, left_expr, base_expr, transfrags = tup
    sgraph = SpliceGraph.create(transfrags)
    cps = run_changepoint(sgraph.expr_data, smooth_window_len=11)
    cp = cps[0]
    assert cp.index == 110
    assert cp.foldchange < 0.5
    assert cp.sign == 1.0
    cps = sgraph.detect_change_points(smooth_window_len=11)
    for cp in cps:
        sgraph.apply_change_point(cp)
    sgraph.recreate()

    assert sgraph.expr_data[0] == 50
    assert sgraph.expr_data[-1] == 250
    assert sgraph.expr_data[cp.index - 1] == base_expr
    assert sgraph.expr_data[cp.index] == 160
    assert cp.pos in sgraph.start_sites
    return


def test_trimming_to_zero_bug():
    t_dict, locus = read_single_locus('change_point_bug.gtf')
    transfrags_un = locus.get_transfrags(Strand.NA)
    sgraph = SpliceGraph.create(transfrags_un)
    cps = sgraph.detect_change_points()
    for cp in cps:
        sgraph.apply_change_point(cp)
    sgraph.recreate()
    # get start/stop nodes
    start_nodes, stop_nodes = sgraph.get_start_stop_nodes()
    # convert to node intervals
    start_nodes = set(sgraph.get_node_interval(n_id) for n_id in start_nodes)
    stop_nodes = set(sgraph.get_node_interval(n_id) for n_id in stop_nodes)
    assert Exon(173433532, 173435169) in stop_nodes
    assert Exon(173433532, 173435169) in start_nodes
    assert Exon(173433532, 173435169) in start_nodes


def test_ccle55_cuff_noc2l():
    '''Locus containing from 55 CCLE samples assembled with Cufflinks'''
    # pull SpliceGraph out of GTF
    t_dict, locus = read_single_locus('noc2l_locus.gtf')
    found_sgraph = False
    for sgraph in locus.create_splice_graphs():
        if (sgraph.chrom == 'chr1' and sgraph.start == 934942 and
            sgraph.end == 976702 and sgraph.strand == Strand.NEG):
            found_sgraph = True
            break
    assert found_sgraph

    # examine specific change points
    trim = False
    pval = 0.05
    fc_cutoff = 0.8
    n1 = Exon(934942, 944589)
    n1_id = sgraph.get_node_id(n1)
    assert sgraph.G.node[n1_id][SGNode.IS_STOP]
    cps = sgraph.detect_change_points(pval=pval, fc_cutoff=fc_cutoff)
    for cp in cps:
        sgraph.apply_change_point(cp, trim=trim)
    true_starts = set([964528, 957434, 959316])
    true_stops = set([944278])
    assert true_starts.issubset(sgraph.start_sites)
    assert true_stops.issubset(sgraph.stop_sites)

    # rebuild graph and examine start/stop nodes
    sgraph.recreate()

    # get start/stop nodes
    start_nodes, stop_nodes = sgraph.get_start_stop_nodes()
    # convert to node intervals
    start_nodes = set(sgraph.get_node_interval(n_id) for n_id in start_nodes)
    stop_nodes = set(sgraph.get_node_interval(n_id) for n_id in stop_nodes)
    assert Exon(959214, 959316) in start_nodes
    assert Exon(959316, 964528) in start_nodes
    assert Exon(957273, 957434) in start_nodes
    assert Exon(944278, 944321) in stop_nodes

    # ensure best path uses change points
    config = Config.defaults()
    config.max_paths = 1
    gene_isoforms = assemble_isoforms(sgraph, config)
    assert len(gene_isoforms) == 1
    isoforms = gene_isoforms[0]
    assert len(isoforms) == 1
    isoform = isoforms[0]
    assert isoform.path[0] == Exon(944321, 944800)
    assert isoform.path[-1] == Exon(959214, 959316)


def get_data(rundir, chrom, start, end, strand):
    filename = os.path.join(rundir, 'expression.h5')
    f = h5py.File(filename, 'r')
    if strand == '+':
        strand_idx = Strand.POS
    elif strand == '-':
        strand_idx = Strand.NEG
    else:
        strand_idx = Strand.NA
    a = f[chrom][strand_idx, start:end]
    return a


def plot_slope(a, refs=None):
    if refs is None:
        refs = []
    smooth_a = np.array(smooth(a, window_len=11, window="hanning"), dtype=FLOAT_DTYPE)
    slope_a = np.gradient(smooth_a)

    plt.figure(1)
    plt.subplot(311)
    plt.plot(a, 'k')
    plt.subplot(312)
    plt.plot(smooth_a, 'g')

    cps = run_changepoint(a, smooth_window_len=11)
# def run_changepoint(a, pval=0.05, fc_cutoff=0.80, size_cutoff=20,
#                     cp_func=mse_cython, smooth_window="hanning",
#                     smooth_window_len=75):

    print 'BUBBA SCHLUMPER', cps
    for cp in cps:
        sign = np.sign(slope_a[cp.index])
        color = 'k'
        if cp.sign == 1: color = 'r'
        if cp.sign == -1: color = 'b'
        plt.axvline(x=cp.index, linewidth=1, color=color)
        for ref in refs:
            plt.axvline(x=ref, linewidth=1, color='m')
    plt.subplot(313)
    plt.plot(slope_a, 'g')
    for cp in cps:
        plt.axvline(x=cp.index - cp.dist_left, linewidth=1, color='y')
        plt.axvline(x=cp.index + cp.dist_right, linewidth=1, color='y')
    plt.show()


def test_anecdotes():

    def tester(tup, ref):
        chrom, start, end, strand = tup
        rundir = '/Users/mkiyer/Documents/lab/projects/taco/ccle/cl1'
        a = get_data(rundir, chrom, start, end, strand)
        print chrom, start, end
        ref_i = []
        for r in ref:
            ref_i.append(r - start)
        plot_slope(a, ref_i)

    tests = [
        ('chr17', 40283388, 40287603, '+'),
        ('chr18', 31042592, 31068212, '-'),
        ('chr17', 40301912, 40314155, '+'),
        ('chr12', 53996031, 54000718, '-'),
        ('chr12', 55992235, 55997163, '+'),
        ('chr12', 56101529, 56104825, '+'),
        ('chr12', 56315821, 56317643, '-'),
        ('chr16', 19551194, 19555731, '+'),
        ('chr18', 31545721, 31550507, '+'),
        ('chr18', 31621550, 31625761, '-'),
        ('chr18', 31630959, 31631146, '-'),
        ('chr18', 31826338, 31830989, '-'),
        ('chr18', 32287031, 32288203, '-'),
        ('chr18', 32089621, 32092235, '+'),
    ]

    #tester(('chr14', 24188807, 24188862, '-'), [])
    #tester(('chr14', 24213498, 24213689, '-'), [])



    #for test in tests:
    #    tester(test, [])
    #
    #
    # tester(('chr1', 11936, 14829, '-'), [14403])
    # tester(('chr1', 183489, 184971, '-'), [184922, 184924, 184926])
    # tester(('chr1', 910143, 917720, '-'), [916869])
    # tester(('chr1', 9268168, 9271563, '+'), [9271337])
    # tester(('chr1', 781937, 793041, '+'), [])
    # tester(('chr1', 778769, 787810, '+'), [])
    # tester(('chr1', 11936, 14829, '-'), [])
