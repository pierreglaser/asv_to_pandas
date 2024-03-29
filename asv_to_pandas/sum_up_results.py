from collections import defaultdict
import itertools
import os
import pathlib

import pandas as pd
import git

from asv.benchmarks import Benchmarks
from asv.config import Config
from asv.commands.publish import Publish


def _get_commit_to_branch_map(repository_path):
    repo = git.Repo(repository_path)
    hash_to_branch_map = {}
    for h in repo.heads:
        hash_to_branch_map[h.commit.hexsha] = h.name
    return hash_to_branch_map


def _remove_quotes(params):
    # params is a list of lists, each list contains the values of one parameter
    unquoted_params_values = []
    for param_values in params:
        unquoted_param_values = []
        for param_value in param_values:
            unquoted_param_values.append(param_value.replace("'", ""))
        unquoted_params_values.append(unquoted_param_values)
    return unquoted_params_values


def _find_asv_root():
    """find the top-level asv directory that includes the current directory"""
    current_dir = pathlib.Path(os.getcwd())
    for dir_ in itertools.chain([current_dir], current_dir.parents):
        if dir_ == pathlib.Path.home():
            # only recurse with user-specific directories
            break
        if 'asv.conf.json' in os.listdir(dir_):
            return str(dir_)
    raise ValueError('Cannot find a current asv benchmark repository')


def create_benchmark_dataframe(group_by="name", use_branch_names=False):
    # if we are in an asv subprocess, use ASV_CONF_DIR to load the config
    repo_dirname = os.environ.get("ASV_CONF_DIR", _find_asv_root())
    config_path = os.path.join(repo_dirname, "asv.conf.json")
    config = Config.load(config_path)

    # results_dir is a relative path to the benchmarks repository. If the
    # directory where the code is run is not the benchmark repository, then
    # loading the results will fail.
    config.results_dir = os.path.join(repo_dirname, "results")

    benchmarks = Benchmarks.load(config)

    results = defaultdict(dict)
    metadata_levels = [
        "type",
        "name",
        "class",
        "file",
        "version",
        "commit_hash",
        "date",
    ]

    if isinstance(group_by, str):
        group_by = [group_by]
    levels_to_group_by = group_by

    levels_to_concat_on = [
        l for l in metadata_levels if l not in levels_to_group_by
    ]

    commit_to_branch_map = _get_commit_to_branch_map(config.repo)

    for single_env_result in Publish.iter_results(config, benchmarks):
        benchmark_metadata = {
            "version": single_env_result._params["python"],
            "commit_hash": single_env_result._commit_hash,
            "date": single_env_result._date,
        }
        if use_branch_names:
            benchmark_metadata["commit_hash"] = commit_to_branch_map.get(
                benchmark_metadata["commit_hash"],
                benchmark_metadata["commit_hash"]
            )

        for b_name, params in single_env_result._benchmark_params.items():
            unquoted_params = _remove_quotes(params)
            filename, classname, benchname = b_name.split(".")

            _benchmark = benchmarks[b_name]
            b_type, param_names = _benchmark["type"], _benchmark["param_names"]

            benchmark_metadata.update(
                {
                    "type": b_type,
                    "file": filename,
                    "class": classname,
                    "name": benchname,
                }
            )

            values_to_group_by = tuple(
                [benchmark_metadata[key] for key in levels_to_group_by]
            )
            values_to_concat_on = tuple(
                [benchmark_metadata[key] for key in levels_to_concat_on]
            )

            # this is dangerous because we there is no reason the results
            # order follow the carthesian product of the parameter space,
            # however empirically it seems to be the case
            params_with_infered_types = []
            _results = single_env_result._results[b_name]
            for params in unquoted_params:
                params_with_infered_types.append(
                    pd.to_numeric(params, errors="ignore"))

            if params_with_infered_types != []:
                mi = pd.MultiIndex.from_product(
                    params_with_infered_types, names=param_names)
            else:
                # benchmark is not parametrized, make index a simple range
                # index
                mi = pd.RangeIndex(len(_results))

            if len(_results) != len(mi):
                # if a benchmark fails, single_env_result._results[b_name]
                # only consists of [None]
                assert _results == [None], 'unexpected benchmark result'
                continue

            _results = pd.Series(_results, index=mi)
            _results.dropna(inplace=True)

            results[values_to_group_by][values_to_concat_on] = _results

    clean_result = {}
    for k, v in results.items():
        if len(k) == 1:
            # if key if a list of length one, convert it to a string by taking
            # its only element
            clean_result[k[0]] = pd.concat(v, names=levels_to_concat_on)
        elif len(k) == 0:
            # if key is of length 0, there is only one element, so, return the
            # underlying dict
            clean_result = pd.concat(v, names=levels_to_concat_on)
        else:
            clean_result[k] = pd.concat(v, names=levels_to_concat_on)

    return clean_result


if __name__ == "__main__":
    all_bench = create_benchmark_dataframe(group_by="class")
