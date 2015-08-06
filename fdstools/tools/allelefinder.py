#!/usr/bin/env python
"""
Find true alleles in reference samples and detect possible
contaminations.

In each sample, the sequences with the highest read counts of each
marker are called alleles, with a user-defined maximum number of alleles
par marker.  The allele balance is kept within given bounds.  If the
highest non-allelic sequence exceeds a given limit, no alleles are
called for this marker.  If this happens for multiple markers in one
sample, no alleles are called for this sample at all.
"""
import argparse
import sys

from ..lib import get_column_ids, pos_int_arg, map_tags_to_files, \
                  add_sample_files_args, ensure_sequence_format, \
                  get_sample_data, add_sequence_format_args, add_output_args

__version__ = "0.1dev"


# Default values for parameters are specified below.

# Default minimum number of reads required for the highest allele.
# This value can be overridden by the -n command line option.
_DEF_MIN_READS = 50

# Default minimum number of reads required for an allele to be called,
# as a percentage of the number of reads of the highest allele.
# This value can be overridden by the -m command line option.
_DEF_MIN_ALLELE_PCT = 30.0

# Default maximum amount of noise to allow, as a percentage of the
# number of reads of the highest allele of each marker.  If any noise
# (i.e., non-allelic sequences) above this threshold are detected, the
# sample is considered 'noisy' for this marker.
# This value can be overridden by the -M command line option.
_DEF_MAX_NOISE_PCT = 10.0

# Default maximum number of alleles to expect for each marker.
# This value can be overridden by the -a command line option.
_DEF_MAX_ALLELES = 2

# Default maximum number of noisy markers allowed per sample.
# This value can be overridden by the -x command line option.
_DEF_MAX_NOISY = 2


def find_alleles(filelist, outfile, reportfile, tag_expr, tag_format,
                 min_reads, min_allele_pct, max_noise_pct, max_alleles,
                 max_noisy, stuttermark_column, seqformat, library):
    if seqformat is not None and library is not None:
        library = parse_library(library)

    outfile.write("\t".join(["sample", "marker", "total", "allele"]) + "\n")
    allelelist = {}
    get_sample_data(
        map_tags_to_files(filelist, tag_expr, tag_format),
        lambda tag, data: find_alleles_sample(
            data if stuttermark_column is None
                 else {key: data[key] for key in allelelist[tag]},
            outfile, reportfile, tag, min_reads, min_allele_pct, max_noise_pct,
            max_alleles, max_noisy, seqformat, library),
        allelelist,
        stuttermark_column)
#find_alleles


def find_alleles_sample(data, outfile, reportfile, tag, min_reads,
                        min_allele_pct, max_noise_pct, max_alleles, max_noisy,
                        seqformat, library):
    top_noise = {}
    top_allele = {}
    alleles = {}
    for marker, allele in data:
        reads = sum(data[marker, allele])

        if marker not in alleles:
            alleles[marker] = {allele: reads}
            top_allele[marker] = reads
            top_noise[marker] = ["-", 0]
        else:
            if reads > top_allele[marker]:
                # New highest allele!
                top_allele[marker] = reads
                for allelex in alleles[marker].keys():
                    if (alleles[marker][allelex] <
                            top_allele[marker] * (min_allele_pct/100.)):
                        if alleles[marker][allelex] > top_noise[marker][1]:
                            top_noise[marker] = [
                                allelex, alleles[marker][allelex]]
                        del alleles[marker][allelex]
                alleles[marker][allele] = reads
            elif reads >= top_allele[marker]*(min_allele_pct/100.):
                # New secundary allele!
                alleles[marker][allele] = reads
            elif reads >= top_noise[marker][1]:
                # New highest noise!
                top_noise[marker] = [allele, reads]

    # Find and eliminate noisy markers in this sample first.
    noisy_markers = 0
    for marker in alleles:
        if top_allele[marker] < min_reads:
            reportfile.write(
                "Sample %s is not suitable for marker %s:\n"
                "highest allele has only %i reads\n\n" %
                    (tag, marker, top_allele[marker]))
            alleles[marker] = {}
            continue
        if len(alleles[marker]) > max_alleles:
            allele_order = sorted(alleles[marker],
                                  key=lambda x: -alleles[marker][x])
            top_noise[marker] = [allele_order[max_alleles],
                alleles[marker][allele_order[max_alleles]]]
            alleles[marker] = {x: alleles[marker][x]
                               for x in allele_order[:max_alleles]}
        if top_noise[marker][1] > top_allele[marker]*(max_noise_pct/100.):
            reportfile.write(
                "Sample %s is not suitable for marker %s:\n"
                "highest non-allele is %.1f%% of the highest allele\n" %
                (tag, marker, 100.*top_noise[marker][1]/top_allele[marker]))
            for allele in sorted(alleles[marker],
                                 key=lambda x: -alleles[marker][x]):
                seq = allele if seqformat is None \
                    else ensure_sequence_format(allele, seqformat,
                        library=library, marker=marker)
                reportfile.write("%i\tALLELE\t%s\n" %
                    (alleles[marker][allele], seq))
            seq = top_noise[marker][0] if seqformat is None \
                else ensure_sequence_format(top_noise[marker][0],
                    seqformat, library=library, marker=marker)
            reportfile.write("%i\tNOISE\t%s\n\n" % (top_noise[marker][1], seq))
            noisy_markers += 1
            alleles[marker] = {}

    # Drop this sample completely if it has too many noisy markers.
    if noisy_markers > max_noisy:
        reportfile.write("Sample %s appears to be contaminated!\n\n" % tag)
        return

    # The sample is OK, write out its alleles.
    for marker in alleles:
        for allele in sorted(alleles[marker],
                             key=lambda x: -alleles[marker][x]):
            seq = allele if seqformat is None else ensure_sequence_format(
                allele, seqformat, library=library, marker=marker)
            outfile.write("\t".join(
                [tag, marker, str(alleles[marker][allele]), seq]) + "\n")
#find_alleles_sample


def add_arguments(parser):
    add_output_args(parser)
    filtergroup = parser.add_argument_group("filtering options")
    filtergroup.add_argument('-m', '--min-allele-pct', metavar="PCT",
        type=float, default=_DEF_MIN_ALLELE_PCT,
        help="call heterozygous if the second allele is at least this "
             "percentage of the highest allele (default: %(default)s)")
    filtergroup.add_argument('-M', '--max-noise-pct', metavar="PCT",
        type=float, default=_DEF_MAX_NOISE_PCT,
        help="a sample is considered contaminated/unsuitable for a marker if "
             "the highest non-allelic sequence is at least this percentage of "
             "the highest allele (default: %(default)s)")
    filtergroup.add_argument('-n', '--min-reads', metavar="N",
        type=pos_int_arg, default=_DEF_MIN_READS,
        help="require at least this number of reads for the highest allele "
             "(default: %(default)s)")
    filtergroup.add_argument('-a', '--max-alleles', metavar="N",
        type=pos_int_arg, default=_DEF_MAX_ALLELES,
        help="allow no more than this number of alleles per marker (default: "
             "%(default)s)")
    filtergroup.add_argument('-x', '--max-noisy', metavar="N",
        type=pos_int_arg, default=_DEF_MAX_NOISY,
        help="entirely reject a sample if more than this number of markers "
             "have a high non-allelic sequence (default: %(default)s)")
    filtergroup.add_argument('-c', '--stuttermark-column', metavar="COLNAME",
        help="name of column with Stuttermark output; if specified, sequences "
             "for which the value in this column does not start with ALLELE "
             "are ignored")
    add_sequence_format_args(parser)
    add_sample_files_args(parser)
#add_arguments


def run(args):
    if args.filelist == [sys.stdin] and sys.stdin.isatty():
        raise ValueError("please specify an input file, or pipe in the output "
                         "of another program")

    find_alleles(args.filelist, args.output, args.report, args.tag_expr,
                 args.tag_format, args.min_reads, args.min_allele_pct,
                 args.max_noise_pct, args.max_alleles, args.max_noisy,
                 args.stuttermark_column, args.sequence_format, args.library)
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
