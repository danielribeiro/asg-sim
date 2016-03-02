import json
import os
import sys
from multiprocessing import Pool

from .cost import cost, run_job


HIGH_RESOLUTION = 10
LOW_RESOLUTION = 60
TRIAL_DURATION_SECS = 100000 # about a day

# Determined from asgsim.plots.static methods
STATIC_MINIMA = [(300, 10.0, 5), (300, 50.0, 12), (300, 200.0, 31),
                 (60, 50.0, 5), (120, 50.0, 7), (600, 50.0, 19), (1200, 50.0, 31)]


def sec_per_tick(*times):
    if any(map(lambda t: t < (LOW_RESOLUTION * 2), times)):
        return HIGH_RESOLUTION
    else:
        return LOW_RESOLUTION


def generate_jobs(jobs, path):
    jobs_per_batch = 100
    for job in jobs:
        job['sec_per_tick'] = sec_per_tick(job['build_run_time'],
                                           job.get('builder_boot_time', 9999),
                                           job.get('alarm_period_duration', 9999))
        job['ticks'] = TRIAL_DURATION_SECS / job['sec_per_tick']
    batch_count = len(jobs) / jobs_per_batch + 1
    for batch in range(batch_count):
        start = batch * jobs_per_batch
        end = start + jobs_per_batch
        batch_jobs = jobs[start:end]
        in_dir = os.path.join(path, 'input')
        if not os.path.isdir(in_dir):
            os.mkdir(in_dir)
        with open(os.path.join(in_dir, '%04d' % batch), 'w') as batch_file:
            json.dump(batch_jobs, batch_file)


def static_jobs(path):
    jobs = [{'autoscale': False,
             'trials': 1000,
             'build_run_time': build_time,
             'builds_per_hour': traffic,
             'initial_builder_count': initial}
            for build_time, traffic, initial in STATIC_MINIMA]
    return jobs


def generate_static_jobs(path):
    generate_jobs(static_jobs(), path)


def autoscaling_jobs():
    up_down_range = [1, 2, 4, 8, 16, 32]
    # Whee! List comprehension!
    jobs = [{'autoscale': True,
             'trials': 5,
             'build_run_time': build_time,
             'builds_per_hour': traffic,
             'builder_boot_time': boot_time,
             'initial_builder_count': initial,
             'alarm_period_duration': alarm_period_duration,
             'alarm_period_count': alarm_period_count,
             'scale_up_threshold': up_threshold,
             'scale_down_threshold': down_threshold,
             'scale_up_change': scale_up_change,
             'scale_down_change': scale_down_change}
            # Start at optimum static fleet sizes
            for build_time, traffic, initial in STATIC_MINIMA
            for boot_time in [10, 30, 60, 120, 300, 600, 1200]
            for alarm_period_duration in [10, 60, 300]
            for alarm_period_count in [1, 2, 4]
            # Assume it's silly for scale_up_threshold > scale_down_threshold
            for up_threshold, down_threshold in [(up, down) for up in up_down_range for down in up_down_range if up <= down]
            for scale_up_change in [1, 2, 4]
            for scale_down_change in [1, 2, 4]]
    return jobs


def generate_autoscaling_jobs():
    generate_jobs(auto_scaling_jobs(), path)


def run_batch(path, batch_name, procs=6):
    in_dir = os.path.join(path, 'input')
    out_dir = os.path.join(path, 'output')
    out_file_path = os.path.join(out_dir, batch_name)
    if os.path.isfile(out_file_path):
        print 'Skipping', batch_name
        return
    else:
        print 'Running', batch_name
    if not os.path.isdir(out_dir):
        os.mkdir(out_dir)
    with open(os.path.join(in_dir, batch_name), 'r') as in_file:
        batch_jobs = json.load(in_file)
    p = Pool(procs)
    try:
        results = p.map(run_job, batch_jobs)
    finally:
        p.close()
        p.join()
    with open(out_file_path, 'w') as out_file:
        json.dump(results, out_file)


def run_batches(path, **kwargs):
    for batch_name in sorted(os.listdir(os.path.join(path, 'input'))):
        run_batch(path, batch_name, **kwargs)


def load_results(path):
    output_path = os.path.join(path, 'output')
    batch_names = sorted(os.listdir(output_path))
    results = []
    for batch_name in batch_names:
        batch_results_path = os.path.join(output_path, batch_name)
        with open(batch_results_path, 'r') as batch_results_file:
            batch_results = json.load(batch_results_file)
            results.extend(batch_results)
    return results


if __name__ == '__main__':
    usage = 'Usage: python -m asgsim.batches <generate-auto|generate-static|run> path [procs]'
    if len(sys.argv) < 3:
        print usage
        exit(1)
    task = sys.argv[1]
    path = sys.argv[2]
    procs = 6
    if len(sys.argv) == 4:
        procs = int(sys.argv[3])
    if sys.argv[1] == 'generate-auto':
        print 'Generating autoscaling jobs in', path
        generate_autoscaling_jobs(sys.argv[2])
    elif sys.argv[1] == 'generate-static':
        print 'Generating static jobs in', path
        generate_static_jobs(sys.argv[2])
    elif sys.argv[1] == 'run':
        print 'Running jobs in %s with %d processes' % (path, procs)
        run_batches(sys.argv[2], procs=procs)
    else:
        print usage
        exit(1)
