#!/usr/bin/env python
"""
Compute allele-centric statistics for background noise in homozygous samples
(min, max, mean, sample variance).
"""
import argparse
import sys

from ..lib import get_column_ids, pos_int_arg, add_sample_files_args,\
                  add_allele_detection_args, map_tags_to_files, adjust_stats,\
                  ensure_sequence_format, parse_allelelist, parse_library,\
                  get_sample_data

__version__ = "0.1dev"


# Default values for parameters are specified below.

# Default minimum amount of background to consider, as a percentage of
# the highest allele.
# This value can be overridden by the -m command line option.
_DEF_THRESHOLD_PCT = 0.5

# Default minimum number of reads to consider.
# This value can be overridden by the -n command line option.
_DEF_THRESHOLD_ABS = 5

# Default minimum number of samples for each true allele.
# This value can be overridden by the -s command line option.
_DEF_MIN_SAMPLES = 2

# Default minimum number of samples required for each background product
# to be included in the analysis, as a percentage of the number of
# samples with a certain true allele.
# This value can be overridden by the -S command line option.
_DEF_MIN_SAMPLE_PCT = 80.


def add_sample_data(data, sample_data, sample_alleles, min_pct, min_abs):
    # Enter the read counts into data and check the thresholds.
    for marker, sequence in sample_data:
        if marker not in sample_alleles:
            # Sample does not participate in this marker.
            continue
        allele = sample_alleles[marker]
        factors = [100./x for x in sample_data[marker, allele]]
        if (marker, allele) not in data:
            data[marker, allele] = {}
        if sequence not in data[marker, allele]:
            data[marker, allele][sequence] = [None, None, 0]
        for direction in (0, 1):
            data[marker, allele][sequence][direction] = adjust_stats(
                sample_data[marker, sequence][direction] * factors[direction],
                data[marker, allele][sequence][direction])
        if sum([count >= min_abs and count*factor >= min_pct
                for count, factor in
                zip(sample_data[marker, sequence], factors)]):
            data[marker, allele][sequence][2] += 1
#add_sample_data


def filter_data(data, min_samples, min_sample_pct):
    """
    Remove all alleles from data that have less than min_samples samples
    and remove all stats of sequences that don't pass the detection
    thresholds in at least min_sample_pct per cent of the samples with a
    particular allele.  Also add explicit zeros to the stats of the
    sequences that were not seen in all samples with a given allele.
    """
    for marker, allele in data.keys():
        if data[marker, allele][allele][2] < min_samples:
            del data[marker, allele]
            continue
        factor = 100./data[marker, allele][allele][2]
        for sequence in data[marker, allele].keys():
            if data[marker, allele][sequence][2] * factor < min_sample_pct:
                del data[marker, allele][sequence]
                continue
            for i in range(data[marker, allele][sequence][0]["n"],
                           data[marker, allele][allele][2]):
                for direction in (0, 1):
                    adjust_stats(0, data[marker, allele][sequence][direction])
#filter_data


def compute_stats(filelist, tag_expr, tag_format, allelefile,
                  annotation_column, min_pct, min_abs, min_samples,
                  min_sample_pct, seqformat, library, marker, limit_reads,
                  drop_samples):

    # Parse library and allele list.
    library = parse_library(library) if library is not None else None
    allelelist = {} if allelefile is None \
                    else parse_allelelist(allelefile, seqformat, library)

    # Read sample data.
    data = {}
    get_sample_data(
        map_tags_to_files(filelist, tag_expr, tag_format),
        lambda tag, sample_data: add_sample_data(
            data, sample_data,
            {m: allelelist[tag][m].pop() for m in allelelist[tag]},
            min_pct, min_abs),
        allelelist, annotation_column, seqformat, library, marker, True,
        limit_reads, drop_samples)

    # Ensure minimum number of samples per allele and filter
    # insignificant background products.
    filter_data(data, min_samples, min_sample_pct)

    print("\t".join(["marker", "allele", "sequence", "n", "fmin", "fmax",
                     "fmean", "fvariance", "rmin", "rmax", "rmean",
                     "rvariance"]))
    for marker, allele in data:
        for sequence in data[marker, allele]:
            print("\t".join([marker, allele, sequence] + [
                str(x) if abs(x) > 0.0000000001 else "0" for x in (
                    data[marker, allele][sequence][0]["n"],
                    data[marker, allele][sequence][0]["min"],
                    data[marker, allele][sequence][0]["max"],
                    data[marker, allele][sequence][0]["mean"],
                    data[marker, allele][sequence][0]["variance"],
                    data[marker, allele][sequence][1]["min"],
                    data[marker, allele][sequence][1]["max"],
                    data[marker, allele][sequence][1]["mean"],
                    data[marker, allele][sequence][1]["variance"])]))
#compute_stats


def add_arguments(parser):
    add_sample_files_args(parser)
    add_allele_detection_args(parser)
    parser.add_argument('-m', '--min-pct', metavar="PCT", type=float,
        default=_DEF_THRESHOLD_PCT,
        help="minimum amount of background to consider, as a percentage "
             "of the highest allele (default: %4.2f)" % _DEF_THRESHOLD_PCT)
    parser.add_argument('-n', '--min-abs', metavar="N", type=pos_int_arg,
        default=_DEF_THRESHOLD_ABS,
        help="minimum amount of background to consider, as an absolute "
             "number of reads (default: %(default)s)")
    parser.add_argument('-s', '--min-samples', metavar="N", type=pos_int_arg,
        default=_DEF_MIN_SAMPLES,
        help="require this minimum number of samples for each true allele "
             "(default: %(default)s)")
    parser.add_argument('-S', '--min-sample-pct', metavar="PCT", type=float,
        default=_DEF_MIN_SAMPLE_PCT,
        help="require this minimum number of samples for each background "
             "product, as a percentage of the number of samples with a "
             "particular true allele (default: %(default)s)")
    parser.add_argument('-F', '--sequence-format', metavar="FORMAT",
        choices=("raw", "tssv", "allelename"),
        help="convert sequences to the specified format: one of %(choices)s "
             "(default: no conversion)")
    parser.add_argument('-l', '--library', metavar="LIBRARY",
        type=argparse.FileType('r'),
        help="library file for sequence format conversion")
    parser.add_argument('-M', '--marker', metavar="MARKER",
        help="work only on MARKER")
    parser.add_argument('-R', '--limit-reads', metavar="N", type=pos_int_arg,
        default=sys.maxint,
        help="simulate lower sequencing depth by randomly dropping reads down "
             "to this maximum total number of reads for each sample")
    parser.add_argument('-x', '--drop-samples', metavar="N", type=float,
        default=0, help="randomly drop this fraction of input samples")
#add_arguments


def run(args):
    if args.filelist == [sys.stdin] and sys.stdin.isatty():
        raise ValueError("please specify an input file, or pipe in the output "
                         "of another program")
    compute_stats(args.filelist, args.tag_expr, args.tag_format,
                  args.allelelist, args.annotation_column, args.min_pct,
                  args.min_abs, args.min_samples, args.min_sample_pct,
                  args.sequence_format, args.library, args.marker,
                  args.limit_reads, args.drop_samples)
#run


def main():
    """
    Main entry point.
    """
    parser = argparse.ArgumentParser(
        description=__doc__)
    try:
        add_arguments(parser)
        run(parser.parse_args())
    except OSError as error:
        parser.error(error)
#main


if __name__ == "__main__":
    main()
