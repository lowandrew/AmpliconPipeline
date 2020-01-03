import os
import glob
import logging
import subprocess


def retrieve_fastqgz(directory: str) -> list:
    """
    :param directory: Path to folder containing output from MiSeq run
    :return: LIST of all .fastq.gz files in directory
    """
    fastq_file_list = glob.glob(os.path.join(directory, '*.fastq.gz'))
    return fastq_file_list


def execute_command(cmd: str) -> tuple:
    """
    :param cmd: String containing command to execute
    :return: Strings for STDOUT and STDERR
    """
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = p.communicate()
    return out.decode('ascii'), err.decode('ascii')


def retrieve_unique_sampleids(fastq_file_list: list) -> list:
    """
    :param fastq_file_list: List of fastq.gz filepaths generated by retrieve_fastqgz()
    :return: List of valid OLC Sample IDs
    """
    logging.info('Scanning for valid OLC sample IDs')
    # Iterate through all of the fastq files and grab the sampleID, append to list
    sample_id_list = list()
    for file in fastq_file_list:
        if valid_olc_id(file):
            sample_id = os.path.basename(file)[:13]  # WARNING: This is specific to the OLC naming scheme
            sample_id_list.append(sample_id)

    # Get unique sample IDs
    sample_id_list = list(set(sample_id_list))

    return sample_id_list


def get_readpair(sample_id: str, fastq_file_list: list, forward_id='_R1', reverse_id='_R2') -> list:
    """
    :param sample_id: String of a valid OLC ID
    :param fastq_file_list: List of fastq.gz file paths generated by retrieve_fastqgz()
    :param forward_id: ID indicating forward read in filename
    :param reverse_id: ID indicating reverse read in filename
    :return: the absolute filepaths of R1 and R2 for a given sample ID
    """

    r1, r2 = None, None
    for file in fastq_file_list:
        if sample_id in os.path.basename(file):
            if forward_id in os.path.basename(file):
                r1 = file
            elif reverse_id in os.path.basename(file):
                r2 = file
    if r1 is not None:
        return [os.path.abspath(r1), os.path.abspath(r2)]
    else:
        logging.debug('Could not pair {}'.format(sample_id))


def populate_sample_dictionary(sample_id_list: list, fastq_file_list: list) -> dict:
    """
    :param sample_id_list: List of unique Sample IDs generated by retrieve_unique_sampleids()
    :param fastq_file_list: List of fastq.gz file paths generated by retrieve_fastqgz()
    :return: dictionary with each Sample ID as a key and the read pairs as values
    """

    # Find file pairs for each unique sample ID
    sample_dictionary = {}
    for sample_id in sample_id_list:
        read_pair = get_readpair(sample_id, fastq_file_list)
        sample_dictionary[sample_id] = read_pair
    return sample_dictionary


def get_sample_dictionary(directory: str) -> dict:
    """
    Chains several functions together to create a sample dictionary with unique/valid sample IDs as keys
    and paths to forward and reverse reads as values
    :param directory: Path to a directory containing .fastq.gz files
    :return: Validated sample dictionary with sample_ID:R1,R2 structure
    """
    fastq_file_list = retrieve_fastqgz(directory)
    sample_id_list = retrieve_unique_sampleids(fastq_file_list)
    sample_dictionary = populate_sample_dictionary(sample_id_list, fastq_file_list)
    return sample_dictionary


def valid_olc_id(filename: str):
    """
    Validate that a fastq.gz file contains a valid OLC sample ID
    :param filename: Path to file
    :return: boolean of valid status
    """
    sample_id = os.path.basename(filename)[:13]
    id_components = sample_id.split('-')
    valid_status = False
    if id_components[0].isdigit() and id_components[1] == 'SEQ' and id_components[2].isdigit():
        valid_status = True
    else:
        logging.warning('WARNING: ID for {} is not a valid OLC ID'.format(sample_id))
    return valid_status


def append_dummy_barcodes(path: str):
    """
    Function to append a dummy barcode ('_00') to all .fastq.gz MiSeq read files for compatibility with QIIME 2
    CasavaOneEightSingleLanePerSampleDirFmt
    :param path: Path to .fastq.gz file
    """
    for file in retrieve_fastqgz(path):
        if valid_olc_id(file):
            # TODO: Make this renaming more robust with some regex
            os.rename(os.path.abspath(file), os.path.abspath(file).replace('_S', '_00_S'))
    logging.info('Added dummy barcodes to all valid OLC *.fastq.gz files in {}'.format(path))


def create_symlink(target, destination_folder):
    os.symlink(target, os.path.join(destination_folder, os.path.basename(target)))


def symlink_dictionary(sample_dictionary: dict, destination_folder: str):
    """
    :param sample_dictionary: Dictionary created with get_sample_dictionary()
    :param destination_folder: Path to folder to generate symlinks
    """
    logging.info('Creating symlinks for samples at {}'.format(destination_folder))
    for key, value in sample_dictionary.items():
        try:
            create_symlink(value[0], destination_folder)
            create_symlink(value[1], destination_folder)
            logging.debug('Created symlinks for {}'.format(key))
        except:
            logging.error('Symbolic links to read pair {} already exist'.format(key))


def create_sampledata_artifact(datadir: str, qiimedir: str) -> str:
    """
    :param datadir: Path to directory containing all symlinks to paired .fastq.gz files for analysis
    :param qiimedir: Path to dump all QIIME 2 output
    :return: Path to QIIME 2 Sample Data Artifact
    """
    cmd = "qiime tools import " \
          "--type 'SampleData[PairedEndSequencesWithQuality]' " \
          "--input-path {datadir} " \
          "--output-path {qiimeout} " \
          "--input-format CasavaOneEightSingleLanePerSampleDirFmt " \
          "".format(datadir=datadir, qiimeout=os.path.join(qiimedir, 'paired-sample-data.qza'))
    out, err = execute_command(cmd)

    if out is not '' or err is not '':
        logging.debug('OUT: {}\nERR: {}'.format(out, err))

    logging.info('Successfully created QIIME 2 data Artifact')
    return os.path.join(qiimedir, 'paired-sample-data.qza')


def project_setup(outdir: str, inputdir: str) -> str:
    # Create folder structure
    os.mkdir(outdir)
    os.mkdir(os.path.join(outdir, 'data'))
    os.mkdir(os.path.join(outdir, 'qiime2'))
    logging.debug('Created QIIME2 analysis folder: {}'.format(outdir))

    # Prepare dictionary containing R1 and R2 for each sample ID
    sample_dictionary = get_sample_dictionary(inputdir)
    logging.debug('Sample Dictionary: {}'.format(sample_dictionary))

    # Create symlinks in data folder
    symlink_dictionary(sample_dictionary=sample_dictionary, destination_folder=os.path.join(outdir, 'data'))

    # Fix symlink filenames for Qiime 2
    append_dummy_barcodes(os.path.join(outdir, 'data'))

    # Call Qiime 2 to create artifact
    logging.info('Creating sample data artifact for QIIME 2...')
    data_artifact_path = create_sampledata_artifact(datadir=os.path.join(outdir, 'data'),
                                                    qiimedir=os.path.join(outdir, 'qiime2'))
    return data_artifact_path


def make_interop_summary(inputdir: str, outdir: str):
    out, err = execute_command("interop_summary " + inputdir)
    if (out[0:9] == "# Version") and (len(out) > 4000):
        try:
            ifile = open(os.path.join(outdir, "interop_summary.csv"), "w")
            ifile.write(out)
            ifile.close()
            logging.info("Made the interop_summary file")
        except:
            logging.info("Couldn't write the interop_summary file!")
    else:
        logging.info("Something went wrong with interop_summary!")

