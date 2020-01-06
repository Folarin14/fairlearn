# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

import os

from fairlearn.postprocessing import ThresholdOptimizer
from fairlearn.reductions import ExponentiatedGradient, GridSearch

from constants import EXPONENTIATED_GRADIENT, THRESHOLD_OPTIMIZER, GRID_SEARCH, \
    AVERAGE_INDIVIDUAL_FAIRNESS_LEARNER


def generate_script(request, perf_test_configuration, script_name, script_directory):
    if not os.path.exists(script_directory):
        os.makedirs(script_directory)

    script_lines = []
    add_imports(script_lines)
    script_lines.append("")
    script_lines.append("run = Run.get_context()")
    add_dataset_setup(script_lines, perf_test_configuration)
    add_unconstrained_estimator_fitting(script_lines, perf_test_configuration)
    script_lines.append('start_time = time()')
    add_mitigation(script_lines, perf_test_configuration)
    add_evaluation(script_lines)
    script_lines.append("")

    print("\n\n{}\n\n".format("="*100))

    with open(os.path.join(script_directory, script_name), 'w') as script_file:  # noqa: E501
        script_file.write("\n".join(script_lines))


def add_imports(script_lines):
    script_lines.append('from time import time')
    script_lines.append('from tempeh.configurations import models, datasets')
    script_lines.append('from fairlearn.postprocessing import ThresholdOptimizer')
    script_lines.append('from fairlearn.reductions import {}, {}, {}'.format(EXPONENTIATED_GRADIENT, GRID_SEARCH, AVERAGE_INDIVIDUAL_FAIRNESS_LEARNER))
    script_lines.append('from fairlearn.reductions import DemographicParity, EqualizedOdds')
    script_lines.append('from azureml.core.run import Run')


def add_dataset_setup(script_lines, perf_test_configuration):
    script_lines.append('print("Downloading dataset")')
    script_lines.append('dataset = datasets["{}"]()'.format(perf_test_configuration.dataset))
    script_lines.append('X_train, X_test = dataset.get_X()')
    script_lines.append('y_train, y_test = dataset.get_y()')
    script_lines.append('print("Done downloading dataset")')

    if perf_test_configuration.dataset == "adult_uci":
        # sensitive feature is 8th column (sex)
        script_lines.append('sensitive_features_train = X_train[:, 7]')
        script_lines.append('sensitive_features_test = X_test[:, 7]')
    elif perf_test_configuration.dataset == "diabetes_sklearn":
        # sensitive feature is 2nd column (sex)
        # features have been scaled, but sensitive feature needs to be str or int
        script_lines.append('sensitive_features_train = X_train[:, 1].astype(str)')
        script_lines.append('sensitive_features_test = X_test[:, 1].astype(str)')
        # labels can't be floats as of now
        script_lines.append('y_train = y_train.astype(int)')
        script_lines.append('y_test = y_test.astype(int)')
    elif perf_test_configuration.dataset == "compas":
        # sensitive feature is either race or sex
        # TODO add another case where we use sex as well, or both (?)
        script_lines.append('sensitive_features_train, sensitive_features_test = dataset.get_sensitive_features("race")')
        script_lines.append('y_train = y_train.astype(int)')
        script_lines.append('y_test = y_test.astype(int)')
    elif perf_test_configuration.dataset == "communities_uci":
        # using this only with average individual fairness right now, so no sensitive features required.
        pass
    else:
        raise ValueError("Sensitive features unknown for dataset {}"
                         .format(perf_test_configuration.dataset))


def add_unconstrained_estimator_fitting(script_lines, perf_test_configuration):
    script_lines.append('print("Fitting estimator")')
    script_lines.append('estimator = models["{}"]()'.format(perf_test_configuration.predictor))
    script_lines.append('unconstrained_predictor = models["{}"]()'.format(perf_test_configuration.predictor))
    script_lines.append('unconstrained_predictor.fit(X_train, y_train)')
    script_lines.append('print("Done fitting estimator")')


def add_mitigation(script_lines, perf_test_configuration):
    requires_sensitive_features = True
    if perf_test_configuration.mitigator == THRESHOLD_OPTIMIZER:
        script_lines.append('mitigator = {}('.format(THRESHOLD_OPTIMIZER) +
                            'unconstrained_predictor=unconstrained_predictor, '
                            'constraints="{}")'.format(perf_test_configuration.disparity_metric))
    elif perf_test_configuration.mitigator == EXPONENTIATED_GRADIENT:
        script_lines.append('mitigator = {}('.format(EXPONENTIATED_GRADIENT) +
                            'estimator=estimator, '
                            'constraints={}())'.format(perf_test_configuration.disparity_metric))
    elif perf_test_configuration.mitigator == GRID_SEARCH:
        script_lines.append('mitigator = {}(estimator=estimator, '.format(GRID_SEARCH) +
                            'constraints={}())'.format(perf_test_configuration.disparity_metric))
    elif perf_test_configuration.mitigator == AVERAGE_INDIVIDUAL_FAIRNESS_LEARNER:
        requires_sensitive_features = False
        script_lines.append('mitigator = {}(T=10)'.format(AVERAGE_INDIVIDUAL_FAIRNESS_LEARNER))
    else:
        raise Exception("Unknown mitigation technique.")

    script_lines.append('print("Fitting mitigator")')
    fit_command = 'mitigator.fit(X_train, y_train{})'
    extra_args = ""
    if requires_sensitive_features:
        extra_args = ', sensitive_features=sensitive_features_train'
    script_lines.append(fit_command.format(extra_args))

    if perf_test_configuration.mitigator == THRESHOLD_OPTIMIZER:
        # ThresholdOptimizer needs sensitive features at test time
        script_lines.append('mitigator.predict('
                            'X_test, '
                            'sensitive_features=sensitive_features_test, '
                            'random_state=1)')
    else:
        script_lines.append('predictions = mitigator.predict(X_test)')


def add_evaluation(script_lines):
    # TODO evaluate accuracy/fairness tradeoff

    script_lines.append('total_time = time() - start_time')
    script_lines.append('run.log("total_time", total_time)')
    script_lines.append('print("Total time taken: {}s".format(total_time))')