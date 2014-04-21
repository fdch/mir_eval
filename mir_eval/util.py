"""Utility sub-module for mir-eval"""

import numpy as np
import os


def index_labels(labels, case_sensitive=False):
    '''Convert a list of string identifiers into numerical indices.

    :parameters:
        - labels : list of strings, shape=(n,)
          A list of annotations, e.g., segment or chord labels from an annotation file.

        - case_sensitive : bool
          Set to `True` to enable case-sensitive label indexing

    :returns:
        - indices : list, shape=(n,)
          Numerical representation of `labels`

        - index_to_label : dict
          Mapping to convert numerical indices back to labels.
          `labels[i] == index_to_label[indices[i]]``
    '''

    label_to_index = {}
    index_to_label = {}

    # If we're not case-sensitive, 
    if not case_sensitive:
        labels = [str(s).lower() for s in labels]

    # First, build the unique label mapping
    for index, s in enumerate(sorted(set(labels))):
        label_to_index[s]       = index
        index_to_label[index]   = s

    # Remap the labels to indices
    indices = [label_to_index[s] for s in labels]

    # Return the converted labels, and the inverse mapping
    return indices, index_to_label

def intervals_to_samples(intervals, labels, offset=0, sample_size=0.1,
                         fill_value=None):
    '''Convert an array of labeled time intervals to annotated samples.

    :parameters:
        - intervals : np.ndarray, shape=(n, d)
            An array of time intervals, as returned by
            ``mir_eval.io.load_annotation``.
            The `i`th interval spans time ``intervals[i, 0]`` to
            ``intervals[i, 1]``.

        - labels : list, shape=(n,)
            The annotation for each interval

        - offset : float > 0
            Phase offset of the sampled time grid (in seconds)

        - sample_size : float > 0
            duration of each sample to be generated (in seconds)

        - fill_value : type(labels[0])
            Object to use for the label with out-of-range time points.

    :returns:
        - sample_times : list
            list of sample times

        - sample_labels : list
            array of segment labels for each generated sample

    ..note::
        Segment intervals will be rounded down to the nearest multiple
        of ``frame_size``.
    '''

    # Round intervals to the sample size
    num_samples = int(np.floor(intervals.max() / sample_size))
    sample_times = (np.arange(num_samples, dtype=np.float32) * sample_size + offset).tolist()
    sampled_labels = interpolate_intervals(
        intervals, labels, sample_times, fill_value)

    return sample_times, sampled_labels

def interpolate_intervals(intervals, labels, time_points, fill_value=None):
    '''Assign labels to a set of points in time given a set of intervals.

    Note: Times outside of the known boundaries are mapped to None by default.

    :parameters:
        - intervals : np.ndarray, shape=(n, d)
            An array of time intervals, as returned by
            ``mir_eval.io.load_annotation``.
            The `i`th interval spans time ``intervals[i, 0]`` to
            ``intervals[i, 1]``.

        - labels : list, shape=(n,)
            The annotation for each interval

        - time_points : array_like, shape=(m,)
            Points in time to assign labels.

    :returns:
        - aligned_labels : list
            Labels corresponding to the given time points.
    '''
    aligned_labels = []
    for tpoint in time_points:
        if tpoint < intervals.min() or tpoint > intervals.max():
            aligned_labels.append(fill_value)
        else:
            index = np.argmax(intervals[:, 0] > tpoint) - 1
            aligned_labels.append(labels[index])
    return aligned_labels

def f_measure(precision, recall, beta=1.0):
    '''Compute the f-measure from precision and recall scores.

    :parameters:
        - precision : float in (0, 1]
            Precision

        - recall : float in (0, 1]
            Recall

        - beta : float > 0
            Weighting factor for f-measure

    :returns:
        - f_measure : float
            The weighted f-measure
    '''

    if precision == 0 and recall == 0:
        return 0.0

    return (1 + beta**2) * precision * recall / ((beta**2) * precision + recall)

def intervals_to_boundaries(intervals):
    '''Convert segment interval times into boundaries.

    :parameters:
      - intervals : np.ndarray, shape=(n_events, 2)
          Array of segment start and end-times

    :returns:
      - boundaries : np.ndarray
          Segment boundary times, including the end of the final segment
    '''

    return np.unique(np.ravel(intervals))

def boundaries_to_intervals(boundaries, labels=None):
    '''Convert an array of event times into intervals

    :parameters:
      - boundaries : list-like
          List of event times

      - labels : None or list of str
          Optional list of strings describing each event

    :returns:
      - segments : np.ndarray, shape=(n_segments, 2)
          Start and end time for each segment

      - labels : list of str or None
          Labels for each event.
    '''

    intervals = np.asarray(zip(boundaries[:-1], boundaries[1:]))

    if labels is None:
        interval_labels = None
    else:
        interval_labels = labels[:-1]

    return intervals, interval_labels

def adjust_intervals(intervals, labels=None, t_min=0.0, t_max=None, label_prefix='__'):
    '''Adjust a list of time intervals to span the range [t_min, t_max].

    Any intervals lying completely outside the specified range will be removed.

    Any intervals lying partially outside the specified range will be truncated.

    If the specified range exceeds the span of the provided data in either direction,
    additional intervals will be appended.  Any appended intervals will be prepended
    with label_prefix.

    :parameters:
        - intervals : np.ndarray, shape=(n_events, 2)
            Array of segment start and end-times

        - labels : list, len=n_events or None
            List of labels

        - t_min : float or None
            Minimum interval start time.

        - t_max : float or None
            Maximum interval end time.

        - label_prefix : str
            Prefix string to use for synthetic labels

    :returns:
        - new_intervals : np.array
            Intervals spanning [t_min, t_max]

        - new_labels : list
            List of labels for new_labels
    '''

    if t_min is not None:
        # Find the intervals that end at or after t_min
        first_idx = np.argwhere(intervals[:, 1] >= t_min)

        if len(first_idx) > 0:
            # If we have events below t_min, crop them out
            if labels is not None:
                labels = labels[int(first_idx[0]):]
            # Clip to the range (t_min, +inf)
            intervals = intervals[int(first_idx[0]):]
        intervals = np.maximum(t_min, intervals)

        if intervals[0, 0] > t_min:
            # Lowest boundary is higher than t_min: add a new boundary and label
            intervals = np.vstack( ([t_min, intervals[0, 0]], intervals) )
            if labels is not None:
                labels.insert(0, '%sT_MIN' % label_prefix)

    if t_max is not None:
        # Find the intervals that begin after t_max
        last_idx = np.argwhere(intervals[:, 0] > t_max)

        if len(last_idx) > 0:
            # We have boundaries above t_max.
            # Trim to only boundaries <= t_max
            if labels is not None:
                labels = labels[:int(last_idx[0])]
            # Clip to the range (-inf, t_max)
            intervals = intervals[:int(last_idx[0])]

        intervals = np.minimum(t_max, intervals)

        if intervals[-1, -1] < t_max:
            # Last boundary is below t_max: add a new boundary and label
            intervals = np.vstack( (intervals, [intervals[-1, -1], t_max]) )
            if labels is not None:
                labels.append('%sT_MAX' % label_prefix)

    return intervals, labels

def adjust_events(events, labels=None, t_min=0.0, t_max=None, label_prefix='__'):
    '''Adjust the given list of event times to span the range [t_min, t_max].

    Any event times outside of the specified range will be removed.

    If the times do not span [t_min, t_max], additional events will be added with
    the prefix label_prefix.

    :parameters:
        - events : np.array
            Array of event times (seconds)

        - labels : list or None
            List of labels

        - t_min : float or None
            Minimum valid event time.

        - t_max : float or None
            Maximum valid event time.

        - label_prefix : str
            Prefix string to use for synthetic labels

    :returns:
        - new_times : np.array
            Event times corrected to the given range.
    '''
    if t_min is not None:
        first_idx = np.argwhere(events >= t_min)

        if len(first_idx) > 0:
            # We have events below t_min
            # Crop them out
            if labels is not None:
                labels = labels[int(first_idx[0]):]
            events = events[int(first_idx[0]):]

        if events[0] > t_min:
            # Lowest boundary is higher than t_min: add a new boundary and label
            events = np.concatenate( ([t_min], events) )
            if labels is not None:
                labels.insert(0, '%sT_MIN' % label_prefix)

    if t_max is not None:
        last_idx = np.argwhere(events> t_max)

        if len(last_idx) > 0:
            # We have boundaries above t_max.
            # Trim to only boundaries <= t_max
            if labels is not None:
                labels = labels[:int(last_idx[0])]
            events = events[:int(last_idx[0])]

        if events[-1] < t_max:
            # Last boundary is below t_max: add a new boundary and label
            events= np.concatenate( (events, [t_max]) )
            if labels is not None:
                labels.append('%sT_MAX' % label_prefix)

    return events, labels

def intersect_files(flist1, flist2):
    '''Return the intersection of two sets of filepaths, based on the file name
    (after the final '/') and ignoring the file extension.

    For example,
    >>> flist1 = ['/a/b/abc.lab', '/c/d/123.lab', '/e/f/xyz.lab']
    >>> flist2 = ['/g/h/xyz.npy', '/i/j/123.txt', '/k/l/456.lab']
    >>> sublist1, sublist2 = instersect_files(flist1, flist2)
    >>> print sublist1
    ['/e/f/xyz.lab',
     '/c/d/123.lab']
    >>> print sublist2
    ['/g/h/xyz.npy',
     '/i/j/123.txt'])

    :parameters:
        - flist1 : list of filepaths
        - flist2 : list of filepaths

    :returns:
        - sublist1 : list of filepaths
        - sublist2 : list of filepaths
    '''
    def fname(abs_path):
        return os.path.splitext(os.path.split(f)[-1])[0]

    fmap = dict([(fname(f), f) for f in flist1])
    pairs = [list(), list()]
    for f in flist2:
        if fname(f) in fmap:
            pairs[0].append(fmap[fname(f)])
            pairs[1].append(f)

    return pairs

def merge_labeled_intervals(x_intervals, x_labels, y_intervals, y_labels):
    r'''Merge the time intervals of two sequences 'x' and 'y'.

    :parameters:
        - x_intervals : np.array
            Array of interval times (seconds)

        - x_labels : list or None
            List of labels

        - y_intervals : np.array
            Array of interval times (seconds)

        - y_labels : list or None
            List of labels

    :returns:
        - new_intervals : np.array
            New interval times of the merged sequences.
        - new_x_labels : list
            New labels for the sequence 'x'
        - new_y_labels : list
            New labels for the sequence 'y'

    :raises:
        - ValueError

    ..note:: The intervals of x and y must be aligned, or previously adjusted
    via 'adjust_intervals'.
    '''
    align_check = [x_intervals[0, 0] == y_intervals[0, 0],
                   x_intervals[-1, 1] == y_intervals[-1, 1]]
    if False in align_check:
        raise ValueError(
            "Time intervals do not align; did you mean to call "
            "'adjust_intervals()' first?")
    time_boundaries = np.unique(
        np.concatenate([x_intervals, y_intervals], axis=0))
    output_intervals = np.array(
        [time_boundaries[:-1], time_boundaries[1:]]).T

    x_labels_out, y_labels_out = [], []
    x_label_range = np.arange(len(x_labels))
    y_label_range = np.arange(len(y_labels))
    for t0, t1 in output_intervals:
        x_idx = x_label_range[(t0 >= x_intervals[:, 0])]
        x_labels_out.append(x_labels[x_idx[-1]])
        y_idx = y_label_range[(t0 >= y_intervals[:, 0])]
        y_labels_out.append(y_labels[y_idx[-1]])
    return output_intervals, x_labels_out, y_labels_out

def _bipartite_match(graph):
    '''Find maximum cardinality matching of a bipartite graph (U,V,E).
    The input format is a dictionary mapping members of U to a list
    of their neighbors in V.

    The output is a dict M mapping members of V to their matches in U.
    '''
    # Adapted from:
    #
    # Hopcroft-Karp bipartite max-cardinality matching and max independent set
    # David Eppstein, UC Irvine, 27 Apr 2002

    # initialize greedy matching (redundant, but faster than full search)
    matching = {}
    for u in graph:
        for v in graph[u]:
            if v not in matching:
                matching[v] = u
                break

    while True:
        # structure residual graph into layers
        # pred[u] gives the neighbor in the previous layer for u in U
        # preds[v] gives a list of neighbors in the previous layer for v in V
        # unmatched gives a list of unmatched vertices in final layer of V,
        # and is also used as a flag value for pred[u] when u is in the first layer
        preds = {}
        unmatched = []
        pred = dict([(u,unmatched) for u in graph])
        for v in matching:
            del pred[matching[v]]
        layer = list(pred)

        # repeatedly extend layering structure by another pair of layers
        while layer and not unmatched:
            newLayer = {}
            for u in layer:
                for v in graph[u]:
                    if v not in preds:
                        newLayer.setdefault(v,[]).append(u)
            layer = []
            for v in newLayer:
                preds[v] = newLayer[v]
                if v in matching:
                    layer.append(matching[v])
                    pred[matching[v]] = v
                else:
                    unmatched.append(v)

        # did we finish layering without finding any alternating paths?
        if not unmatched:
            unlayered = {}
            for u in graph:
                for v in graph[u]:
                    if v not in preds:
                        unlayered[v] = None
            return matching

        # recursively search backward through layers to find alternating paths
        # recursion returns true if found path, false otherwise
        def recurse(v):
            if v in preds:
                L = preds[v]
                del preds[v]
                for u in L:
                    if u in pred:
                        pu = pred[u]
                        del pred[u]
                        if pu is unmatched or recurse(pu):
                            matching[v] = u
                            return 1
            return 0

        for v in unmatched:
            recurse(v)

def match_events(ref, est, window):
    '''Compute a maximum matching between reference and estimated event times, subject to a window constraint.

    Given two list of event times `ref` and `est`, we seek the largest set of correspondences `(ref[i], est[j])`
    such that `|ref[i] - est[j]| <= window`, and each `ref[i]` and `est[j]` is matched at most once.

    This is useful for computing precision/recall metrics in beat tracking, onset detection, and segmentation.

    :parameters:
        - ref : np.ndarray, shape=(n,)
          Array of reference event times

        - est : np.ndarray, shape=(m,)
          Array of estimated event times

        - window : float > 0
          Size of the window.

    :returns:
        - matching : list of tuples
          A list of matched reference and event numbers.
          `matching[i] == (i, j)` where `ref[i]` matches `est[j]`.
    '''

    # Compute the indices of feasible pairings
    hits = np.where(np.abs(np.subtract.outer(ref, est)) <= window)

    # Construct the graph input
    G = {}
    for ref_i, est_i in zip(*hits):
        if ref_i not in G:
            G[ref_i] = []
        G[ref_i].append(est_i)

    # Compute the maximum matching
    matching = sorted(_bipartite_match(G).items())

    return matching
