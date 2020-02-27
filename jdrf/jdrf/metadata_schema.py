from collections import defaultdict
import re

from pandas_schema import Column, Schema
from pandas_schema.validation import (LeadingWhitespaceValidation, TrailingWhitespaceValidation, 
                                      CanConvertValidation, MatchesPatternValidation, CustomSeriesValidation,
                                      InRangeValidation, InListValidation, DateFormatValidation)


study_schema = Schema([
    Column('study_id', [CustomSeriesValidation(lambda x: ~x.isnull(), 'A value is required for the study_id column.') &
                        ~InListValidation([''])]),
    Column('pi_name', [CustomSeriesValidation(lambda x: ~x.isnull(), 'A value is required for the pi_name column.') &
                        ~InListValidation([''])]),
    Column('sample_type', [InListValidation(['wmgx', 'wmtx', '16S', 'other'])]),
    Column('bioproject_accession', [InListValidation(['']) | MatchesPatternValidation(r'PRJ\w+\d+')]),
    Column('geo_loc_name', [InListValidation(['']) | MatchesPatternValidation(r'\w+:\w+:\w+')]),
    Column('analysis_desc', [InListValidation(['']) | CanConvertValidation(str)]),
    Column('sequencing_facility', [LeadingWhitespaceValidation()]),
    Column('env_biom', [MatchesPatternValidation(r'ENVO:\d+') | InListValidation([''])]),
    Column('env_feature', [MatchesPatternValidation(r'ENVO:\d+') | InListValidation([''])]),
    Column('env_material', [MatchesPatternValidation(r'ENVO:\d+') | InListValidation([''])]),
    Column('host_tissue_sampled', [InListValidation(['']) | MatchesPatternValidation(r'BTO:\d+')]),
    Column('animal_vendor', [LeadingWhitespaceValidation()]),
    Column('paired', [InListValidation(['true', 'false'])]),
    Column('paired_id', [InListValidation(['']) | MatchesPatternValidation(r'[a-zA-Z0-9_.]+')])
    ,
    Column('pi_email', [CustomSeriesValidation(lambda x: ~x.isnull(), 'A value is required for the pi_email column.') &
                        ~InListValidation([''])])
])

sample_schema = Schema([
    Column('host_subject_id', [MatchesPatternValidation(r'\w+', message='Host Subject ID may only contain alphanumeric characters.')]),
    Column('host_diet', [LeadingWhitespaceValidation()]),
    Column('source_material_id', [LeadingWhitespaceValidation()]),
    Column('ethnicity', [CanConvertValidation(str, message='Ethnicity may only contain alphanumeric characters.')]),
    Column('host_family_relationship', [LeadingWhitespaceValidation()]),
    Column('host_genotype', [LeadingWhitespaceValidation() |
                             MatchesPatternValidation(r'^[http|www]', message='Host Genotype may only be a valid URL to the associated DbGap project.')]),
    Column('isolation_source', [LeadingWhitespaceValidation()]), 
    Column('samp_mat_process', [LeadingWhitespaceValidation()]),
    Column('filename', [CustomSeriesValidation(lambda x: ~x.isnull(), 'A value is required for the filename column.'),
                        MatchesPatternValidation(r'\w+.[fastq|fasta|fq|raw](.gz)?', message='Filename must be a valid fasta/fastq file with the following supported extensions: .fasta.gz, .fastq.gz, fq.gz')]),
    Column('sample_id', [CustomSeriesValidation(lambda x: ~x.isnull(), 'A value is required for the sample_id column.')]),
    Column('collection_date', [CustomSeriesValidation(lambda x: ~x.isnull(), 'A value is required for the collection_date column.'),
                               DateFormatValidation('%Y-%m-%d', message='Collection date must be in YYYY-MM-DD date format.')]),
    Column('subject_tax_id', [InListValidation(['10090', '9606'])]),
    Column('subject_age', [CustomSeriesValidation(lambda x: ~x.isnull(), 'A value is required for the subject_age column.'),
                           InRangeValidation(0, 120)]),
    Column('subject_sex', [CustomSeriesValidation(lambda x: ~x.isnull(), 'A value is required for the subject_sex column.'),
                           InListValidation(['M', 'm', 'F', 'f'])]),
    Column('md5_checksum', [CustomSeriesValidation(lambda x: ~x.isnull(), 'A value is required for the md5_checksum column.'),
                            MatchesPatternValidation(r'[a-zA-Z0-9]{32}', message='MD5 Checksum may only contain 32 alphanumeric characters.')]),
    Column('host_body_mass_index', [LeadingWhitespaceValidation() | CanConvertValidation(float)]),
    Column('host_disease', [LeadingWhitespaceValidation() | 
                            MatchesPatternValidation(r'DOID:\d+', message='Must provide a valid Disease Ontology ID in format \'DOID:<NUMBERS>\'')]),
    Column('variable_region', [CustomSeriesValidation(lambda x: ~x.isnull(), '') |
                               MatchesPatternValidation(r'(V[1-9],?)+', message='Variable region must be a valid 16S hypervariable region.')]),
    Column('gastrointest_disord', [LeadingWhitespaceValidation() | CanConvertValidation(int)]),
    Column('host_body_product', [LeadingWhitespaceValidation() |
                                 MatchesPatternValidation(r'GENEPIO_\d+', message='Must provide a valid Genetic epidemiology ontology ID in format \'GENEPIO_<NUMBERS>\'')]),
    Column('host_phenotype', [LeadingWhitespaceValidation() | CanConvertValidation(int)]),
    Column('ihmc_medication_code', [CustomSeriesValidation(lambda x: ~x.isnull(), '') |
                                    MatchesPatternValidation(r'(\d+,?)+]', message='IHMC medication code must be a number.')]),
    Column('organism_count', [CustomSeriesValidation(lambda x: ~x.isnull(), '') |
                              InRangeValidation(1, message='Organism count must be a positive number.')]),
    Column('samp_store_dur', [LeadingWhitespaceValidation() | 
                              InRangeValidation(1, message='Sample storage duration must be a positive number.')]),
    Column('samp_store_temp', [LeadingWhitespaceValidation() | 
                               CanConvertValidation(int, message='Sample storage temperature must be a valid temperature number.')]),
    Column('samp_vol_mass', [LeadingWhitespaceValidation() |
                             MatchesPatternValidation(r'\d+[.]?\d*(g|ml)', message='Sample volume mass must be in format <NUMBER>g or <NUMBER>ml')]),
    Column('sequencer', [InListValidation(["Illumina MiSeq", "Illumina NextSeq", "illumina miseq", "illumina nextseq",
                                           "Illumina HiSeq", "Illumina HiSeq X", "illumina hiseq", "illumina hiseq x",
                                           "PacBio Sequel", "Nanopore MinION", "pacbio sequel", "nanopore minion",
                                           "Nanopore PromethION", "Nanopore SmidgION", "nanopore promethion", "nanopore smidgion",
                                           "454", "Sanger", "sanger", "Ion torrent", "ion torrent", "NA", "N/A"])]),
    Column('read_number', [LeadingWhitespaceValidation() |
                           InRangeValidation(1, message='Read number must be a positive number.')])
])

sample_optional_cols = set(['read_number','host_body_mass_index','host_diet','host_disease','source_material_id',
                            'variable_region','ethnicity','gastrointest_disord','host_body_product','host_family_relationship',
                            'host_genotype','host_phenotype','ihmc_medication_code','isolation_source','organism_count',
                            'samp_mat_process','samp_store_dur','samp_store_temp','samp_vol_mass'])

schemas = {'sample': sample_schema, 'study': study_schema}

# Credit to https://stackoverflow.com/a/14323887
#
# Parses our weird PHP-format querystrings that DataTables Editor sends to a 
# normal python looking dictionary.
def split(string, brackets_on_first_result = False):
    matches = re.split("[\[\]]+", string)
    matches.remove('')
    return matches


def mr_parse(params):
    results = {}
    for key in params:
        if '[' in key:
            key_list = split(key)
            d = results
            for partial_key in key_list[:-1]:
                if partial_key not in d:
                    d[partial_key] = dict()
                d = d[partial_key]
            d[key_list[-1]] = params[key]
        else:
            results[key] = params[key]
    return results
