"""
Functions for actions pertaining to history files.
"""

from CIME.XML.standard_module_setup import *

import logging, glob, os, shutil, re
logger = logging.getLogger(__name__)

def _iter_model_file_substrs(case):
    models = case.get_compset_components()
    models.append('cpl')
    for model in models:
        yield model

def _get_all_hist_files(testcase, model, from_dir, suffix=""):
    suffix = (".%s" % suffix) if suffix else ""

    # Match hist files produced by run
    test_hists = glob.glob("%s/%s.%s*.h?.nc%s" % (from_dir, testcase, model, suffix))
    test_hists.extend(glob.glob("%s/%s.%s*.h.nc%s" % (from_dir, testcase, model, suffix)))

    # Match multi-instance files produced by run
    test_hists.extend(glob.glob("%s/%s.%s*.h?.*.nc%s" % (from_dir, testcase, model, suffix)))
    test_hists.extend(glob.glob("%s/%s.%s*.h.*.nc%s" % (from_dir, testcase, model, suffix)))

    # suffix == "" implies baseline comparison, baseline hist files have simpler names
    if suffix == "":
        test_hists.extend(glob.glob("%s/%s.h.nc" % (from_dir, model)))
        test_hists.extend(glob.glob("%s/%s.h?.nc" % (from_dir, model)))
        test_hists.extend(glob.glob("%s/%s.h.*.nc" % (from_dir, model)))
        test_hists.extend(glob.glob("%s/%s.h?.*.nc" % (from_dir, model)))

    test_hists.sort()
    return test_hists

def _get_latest_hist_files(testcase, model, from_dir, suffix=""):
    test_hists = _get_all_hist_files(testcase, model, from_dir, suffix)
    latest_files = {}
    histlist = []
    date_match = re.compile(r"(\d\d\d\d)-(\d\d)-(\d\d)-(\d\d\d\d\d).nc")
    for hist in test_hists:
        ext = get_extension(model, hist)
        if ext in latest_files:
            s1 = date_match.search(hist)
            if s1 is None:
                latest_files[ext] = hist
                continue
            (yr,month,day,time) = s1.group(1,2,3,4)
            s2 = date_match.search(latest_files[ext])
            (pyr,pmonth,pday,ptime) = s2.group(1,2,3,4)
            if yr > pyr or (yr == pyr and month > pmonth) or \
                    (yr == pyr and month == pmonth and day > pday) or \
                    (yr == pyr and month == pmonth and day == pday and time > ptime):
                latest_files[ext] = hist
                logger.debug("ext %s hist %s %s"%(ext,hist,latest_files))
        else:
            latest_files[ext] = hist

    for key in latest_files.keys():
        histlist.append(latest_files[key])
    return histlist


def move(case, suffix):
    """
    Change the suffix for the most recent batch of hist files in a case. This can
    allow you to temporarily "save" these files so they won't be blown away if you
    re-run the case.

    case - The case containing the files you want to save
    suffix - The string suffix you want to add to saved files, this can be used to find them later.
    """
    rundir   = case.get_value("RUNDIR")
    testcase = case.get_value("CASE")

    # Loop over models
    comments = "Moving hist files to suffix '%s'\n" % suffix
    num_moved = 0
    for model in _iter_model_file_substrs(case):
        comments += "  Moving hist files for model '%s'\n" % model
        test_hists = _get_latest_hist_files(testcase, model, rundir)
        num_moved += len(test_hists)
        for test_hist in test_hists:
            new_file = "%s.%s" % (test_hist, suffix)
            if os.path.exists(new_file):
                os.remove(new_file)

            comments += "    Copying '%s' to '%s'\n" % (test_hist, new_file)
            shutil.copy(test_hist, new_file)

    expect(num_moved > 0, "move failed: no hist files found in rundir '%s'" % rundir)

    return comments

def _hists_match(model, hists1, hists2, suffix1="", suffix2=""):
    """
    return (num in set 1 but not 2 , num in set 2 but not 1, matchups)

    >>> hists1 = ['FOO.G.cpl.h1.nc', 'FOO.G.cpl.h2.nc', 'FOO.G.cpl.h3.nc']
    >>> hists2 = ['cpl.h2.nc', 'cpl.h3.nc', 'cpl.h4.nc']
    >>> _hists_match('cpl', hists1, hists2)
    (['FOO.G.cpl.h1.nc'], ['cpl.h4.nc'], [('FOO.G.cpl.h2.nc', 'cpl.h2.nc'), ('FOO.G.cpl.h3.nc', 'cpl.h3.nc')])
    >>> hists1 = ['FOO.G.cpl.h1.nc.SUF1', 'FOO.G.cpl.h2.nc.SUF1', 'FOO.G.cpl.h3.nc.SUF1']
    >>> hists2 = ['cpl.h2.nc.SUF2', 'cpl.h3.nc.SUF2', 'cpl.h4.nc.SUF2']
    >>> _hists_match('cpl', hists1, hists2, 'SUF1', 'SUF2')
    (['FOO.G.cpl.h1.nc.SUF1'], ['cpl.h4.nc.SUF2'], [('FOO.G.cpl.h2.nc.SUF1', 'cpl.h2.nc.SUF2'), ('FOO.G.cpl.h3.nc.SUF1', 'cpl.h3.nc.SUF2')])
    """
    normalized1, normalized2 = [], []
    for hists, suffix, normalized in [(hists1, suffix1, normalized1), (hists2, suffix2, normalized2)]:
        for hist in hists:
            normalized_name = hist[hist.rfind(model):]
            if suffix1 != "":
                expect(normalized_name.endswith(suffix), "How did '%s' hot have suffix '%s'" % (hist, suffix))
                normalized_name = normalized_name[:len(normalized_name) - len(suffix)]

            normalized.append(normalized_name)

    set_of_1_not_2 = set(normalized1) - set(normalized2)
    set_of_2_not_1 = set(normalized2) - set(normalized1)

    one_not_two = sorted([hists1[normalized1.index(item)] for item in set_of_1_not_2])
    two_not_one = sorted([hists2[normalized2.index(item)] for item in set_of_2_not_1])

    both = set(normalized1) & set(normalized2)
    match_ups = sorted([ (hists1[normalized1.index(item)], hists2[normalized2.index(item)]) for item in both])
    expect(len(match_ups) + len(set_of_1_not_2) == len(hists1), "Programming error1")
    expect(len(match_ups) + len(set_of_2_not_1) == len(hists2), "Programming error2")

    return one_not_two, two_not_one, match_ups

def _compare_hists(case, from_dir1, from_dir2, suffix1="", suffix2=""):
    if from_dir1 == from_dir2:
        expect(suffix1 != suffix2, "Comparing files to themselves?")

    testcase = case.get_value("CASE")
    all_success = True
    num_compared = 0
    comments = "Comparing hists for case '%s' dir1='%s', suffix1='%s',  dir2='%s' suffix2='%s'\n" % \
        (testcase, from_dir1, suffix1, from_dir2, suffix2)

    for model in _iter_model_file_substrs(case):
        comments += "  comparing model '%s'\n" % model
        hists1 = _get_latest_hist_files(testcase, model, from_dir1, suffix1)
        hists2 = _get_latest_hist_files(testcase, model, from_dir2, suffix2)

        if len(hists1) == 0 and len(hists2) == 0:
            comments += "    no hist files found for model %s\n" % model
            continue

        one_not_two, two_not_one, match_ups = _hists_match(model, hists1, hists2, suffix1, suffix2)
        for item in one_not_two:
            comments += "    File '%s' had no counterpart in '%s' with suffix '%s'\n" % (item, from_dir2, suffix2)
            all_success = False
        for item in two_not_one:
            comments += "    File '%s' had no counterpart in '%s' with suffix '%s'\n" % (item, from_dir1, suffix1)
            all_success = False

        num_compared += len(match_ups)
        for hist1, hist2 in match_ups:
            success, cprnc_comments = cprnc(hist1, hist2, case, from_dir1)
            if success:
                comments += "    %s matched %s\n" % (hist1, hist2)
            else:
                comments += "    %s did NOT match %s\n" % (hist1, hist2)
                comments += cprnc_comments + "\n"
                all_success = False

    expect(num_compared > 0, "Did not compare any hist files for suffix1='%s' suffix2='%s', dir1='%s', dir2='%s'\nComments=%s" %
           (suffix1, suffix2, from_dir1, from_dir2, comments))
    return all_success, comments

def compare_test(case, suffix1, suffix2):
    """
    Compares two sets of component history files in the testcase directory

    case - The case containing the hist files to compare
    suffix1 - The suffix that identifies the first batch of hist files
    suffix1 - The suffix that identifies the second batch of hist files

    returns (SUCCESS, comments)
    """
    rundir   = case.get_value("RUNDIR")

    return _compare_hists(case, rundir, rundir, suffix1, suffix2)

def cprnc(file1, file2, case, rundir):
    """
    Run cprnc to compare two individual nc files

    file1 - the full or relative path of the first file
    file2 - the full or relative path of the second file
    case - the case containing the files
    rundir - the rundir for the case

    returns True if the files matched
    """
    cprnc_exe = case.get_value("CCSM_CPRNC")
    basename = os.path.basename(file1)
    stat, out, _ = run_cmd("%s -m %s %s 2>&1 | tee %s/%s.cprnc.out" % (cprnc_exe, file1, file2, rundir, basename))
    return (stat == 0 and "files seem to be IDENTICAL" in out, out)

def compare_baseline(case, baseline_dir=None):
    """
    compare the current test output to a baseline result

    case - The case containing the hist files to be compared against baselines
    baseline_dir - Optionally, specify a specific baseline dir, otherwise it will be computed from case config

    returns (SUCCESS, comments)
    SUCCESS means all hist files matched their corresponding baseline
    """
    rundir   = case.get_value("RUNDIR")
    if baseline_dir is None:
        baselineroot = case.get_value("BASELINE_ROOT")
        basecmp_dir = os.path.join(baselineroot, case.get_value("BASECMP_CASE"))
        dirs_to_check = (baselineroot, basecmp_dir)
    else:
        basecmp_dir = baseline_dir
        dirs_to_check = (basecmp_dir,)

    for bdir in dirs_to_check:
        if not os.path.isdir(bdir):
            return False, "ERROR baseline directory '%s' does not exist" % bdir

    return _compare_hists(case, rundir, basecmp_dir)

def get_extension(model, filepath):
    """
    For a hist file for the given model, return what we call the "extension"

    model - The component model
    filepath - The path of the hist file

    >>> get_extension("cpl", "cpl.hi.nc")
    'hi'
    >>> get_extension("cpl", "cpl.h.nc")
    'h'
    >>> get_extension("cpl", "cpl.h1.nc")
    'h1'
    >>> get_extension("cpl", "TESTRUNDIFF_Mmpi-serial.f19_g16_rx1.A.melvin_gnu.C.fake_testing_only_20160816_164150-20160816_164240.cpl.hi.0.nc.base")
    'hi'
    >>> get_extension("cpl", "TESTRUNDIFF_Mmpi-serial.f19_g16_rx1.A.melvin_gnu.C.fake_testing_only_20160816_164150-20160816_164240.cpl.h.nc")
    'h'
    """
    basename = os.path.basename(filepath)
    ext_regex = re.compile(r'.*%s.*[.](h.?)([.][^.]+)?[.]nc' % model)
    m = ext_regex.match(basename)
    expect(m is not None, "Failed to get extension for file '%s'" % filepath)
    return m.groups()[0]

def generate_baseline(case, baseline_dir=None):
    """
    copy the current test output to baseline result

    case - The case containing the hist files to be copied into baselines
    baseline_dir - Optionally, specify a specific baseline dir, otherwise it will be computed from case config

    returns (SUCCESS, comments)
    """
    rundir   = case.get_value("RUNDIR")
    if baseline_dir is None:
        baselineroot = case.get_value("BASELINE_ROOT")
        basegen_dir = os.path.join(baselineroot, case.get_value("BASEGEN_CASE"))
    else:
        basegen_dir = baseline_dir
    testcase = case.get_value("CASE")

    if not os.path.isdir(basegen_dir):
        os.makedirs(basegen_dir)

    comments = "Generating baselines into '%s'\n" % basegen_dir
    num_gen = 0
    for model in _iter_model_file_substrs(case):
        comments += "  generating for model '%s'\n" % model
        hists =  _get_latest_hist_files(testcase, model, rundir)
        logger.debug("latest_files: %s" % hists)
        num_gen += len(hists)
        for hist in hists:
            basename = hist[hist.rfind(model):]
            baseline = os.path.join(basegen_dir, basename)
            if os.path.exists(baseline):
                os.remove(baseline)

            shutil.copy(hist, baseline)
            comments += "    generating baseline '%s' from file %s\n" % (baseline, hist)

    expect(num_gen > 0, "Could not generate any hist files for case '%s', something is seriously wrong" % testcase)

    return True, comments