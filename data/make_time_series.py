#
# Visualization Vignettes
#
# make_time_series.py -- build the XML time series that actually carries time
#
# WHY THIS EXISTS
#
#   The shipped legacy series, data/varying_data/varying*.vtk, carries no time
#   and no cycle. Nothing in those files says which timestep they are. Both
#   ParaView and VisIt therefore *synthesize* a time from the file's position
#   in the series, and for years they agreed by coincidence rather than by
#   reading anything.
#
#   VisIt 3.4.2 changed what it synthesizes -- from the state index to zero --
#   and the coincidence ended:
#
#       series as shipped        ParaView 6.1.0   VisIt 3.4.1   VisIt 3.4.2
#       legacy .vtk              0, 1, 2 ...      0, 1, 2 ...   0, 0, 0 ...
#
#   No amount of fixing the vignette makes that right, because the vignette
#   was never reading a time. A time series with no time in it cannot
#   demonstrate how two codes handle time; it can only demonstrate how they
#   guess.
#
#   Nor can it be fixed in place. Measured, on the same twenty files:
#
#     * !TIME directives in the .visit index are IGNORED by 3.4.1 and 3.4.2
#       alike, even though that is the documented mechanism;
#     * TIME/CYCLE in the legacy file's FieldData works in both VisIt
#       versions, and is IGNORED by ParaView's LegacyVTKReader;
#     * a .pvd collection over legacy .vtk files yields no timesteps at all,
#       because PVDReader wants XML.
#
#   XML is the one format where both codes read the same real values:
#
#       .vtr + .pvd (ParaView) / .visit (VisIt)
#       ParaView 6.1.0  [0.0, 0.05, 0.1, 0.15, 0.2]
#       VisIt 3.4.1     (0.0, 0.05, 0.1, 0.15, 0.2)  cycles (0, 100, 200, ...)
#       VisIt 3.4.2     (0.0, 0.05, 0.1, 0.15, 0.2)  cycles (0, 100, 200, ...)
#
#   So this converts the series once, per machine, writing both index files.
#   The time is deliberately NOT the file index -- dt is 0.05 and the cycle
#   step is 100 -- so that "timestep", "cycle" and "time" are three visibly
#   different numbers. A vignette that reports all three is then demonstrating
#   something rather than restating the loop counter three times.
#
#   The legacy series stays exactly where it is. ex07, ex10 and ex11 keep
#   reading it, and ex11's ParaView state keeps exercising LegacyVTKReader,
#   which is the point of that vignette. ex05 and ex12, the two whose subject
#   IS time, read this one.
#
# OUTPUT (generated, not committed -- see .gitignore)
#
#   data/varying_series_xml/varying000.vtr ...   one per timestep
#   data/varying_series_xml/series.pvd           ParaView index, real times
#   data/varying_series_xml/series.visit         VisIt index
#   data/varying_series_xml/manifest.json        provenance and the time table
#
# USAGE
#
#   pvbatch data/make_time_series.py
#   python3 Testing/prepare_machine.py           # which is what calls it
#
# Author: James Kress, <james@jameskress.com>
#
from __future__ import print_function

import argparse
import datetime
import glob
import json
import os
import sys

import paraview
from paraview.simple import *  # noqa: F401,F403
import vtk


# A simulation time and cycle that are NOT the loop counter. The whole point
# is that a reader has to have read the file to know them.
TIME_STEP = 0.05
CYCLE_STEP = 100


def log(message):
    print("[make_time_series] {0}".format(message))
    sys.stdout.flush()


def read_legacy(path):
    """Read one legacy rectilinear .vtk into a vtkRectilinearGrid."""
    reader = vtk.vtkRectilinearGridReader()
    reader.SetFileName(path)
    reader.ReadAllScalarsOn()
    reader.ReadAllVectorsOn()
    reader.ReadAllFieldsOn()
    reader.Update()
    grid = vtk.vtkRectilinearGrid()
    grid.ShallowCopy(reader.GetOutput())
    if grid.GetNumberOfPoints() == 0:
        raise RuntimeError("no points read from {0}".format(path))
    return grid


def stamp(grid, time_value, cycle):
    """Put TIME and CYCLE into the dataset's field data.

    VisIt's XML reader picks both up from here. ParaView gets its times from
    the .pvd instead, so this is belt and braces -- but it is also what makes
    a single .vtr correct on its own, without an index file, which matters
    the moment somebody opens one by hand.
    """
    time_array = vtk.vtkDoubleArray()
    time_array.SetName("TIME")
    time_array.SetNumberOfTuples(1)
    time_array.SetValue(0, float(time_value))

    cycle_array = vtk.vtkIntArray()
    cycle_array.SetName("CYCLE")
    cycle_array.SetNumberOfTuples(1)
    cycle_array.SetValue(0, int(cycle))

    grid.GetFieldData().AddArray(time_array)
    grid.GetFieldData().AddArray(cycle_array)


def write_vtr(grid, path):
    writer = vtk.vtkXMLRectilinearGridWriter()
    writer.SetFileName(path)
    writer.SetDataModeToBinary()
    writer.SetCompressorTypeToZLib()
    writer.SetInputData(grid)
    if not writer.Write():
        raise RuntimeError("failed to write {0}".format(path))


def write_pvd(path, entries):
    """ParaView's index. The timestep attribute is what it reads."""
    lines = [
        '<?xml version="1.0"?>',
        '<VTKFile type="Collection" version="0.1" byte_order="LittleEndian">',
        "  <Collection>",
    ]
    for time_value, filename in entries:
        lines.append(
            '    <DataSet timestep="{0!r}" group="" part="0" '
            'file="{1}"/>'.format(float(time_value), filename)
        )
    lines += ["  </Collection>", "</VTKFile>"]
    with open(path, "w") as handle:
        handle.write("\n".join(lines) + "\n")


def write_visit_index(path, entries):
    """VisIt's index.

    Relative filenames, deliberately: a .visit resolves them against its own
    directory, so the series survives the repository being moved or copied.
    !TIME lines are not written because VisIt ignores them (measured on 3.4.1
    and 3.4.2); the times come out of each file's FieldData instead.
    """
    with open(path, "w") as handle:
        handle.write("!NBLOCKS 1\n")
        for _time_value, filename in entries:
            handle.write(filename + "\n")


def main(argv=None):
    here = os.path.abspath(os.path.dirname(os.path.abspath(__file__)))

    parser = argparse.ArgumentParser(
        description="Convert the legacy varying*.vtk series into an XML "
        "series that carries real times and cycles.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--source-dir", default=os.path.join(here, "varying_data"))
    parser.add_argument(
        "--output-dir", default=os.path.join(here, "varying_series_xml")
    )
    parser.add_argument("--time-step", type=float, default=TIME_STEP)
    parser.add_argument("--cycle-step", type=int, default=CYCLE_STEP)
    args, _unknown = parser.parse_known_args(argv)

    source = sorted(glob.glob(os.path.join(args.source_dir, "*.vtk")))
    if not source:
        raise RuntimeError(
            "No .vtk files in {0}. Run data/fetchData.sh first.".format(args.source_dir)
        )
    log("source: {0} timestep(s) in {1}".format(len(source), args.source_dir))

    if not os.path.isdir(args.output_dir):
        os.makedirs(args.output_dir)

    entries = []
    table = []
    for index, path in enumerate(source):
        time_value = round(index * args.time_step, 10)
        cycle = index * args.cycle_step
        grid = read_legacy(path)
        stamp(grid, time_value, cycle)
        name = "varying{0:03d}.vtr".format(index)
        write_vtr(grid, os.path.join(args.output_dir, name))
        entries.append((time_value, name))
        table.append(
            {
                "timestep": index,
                "cycle": cycle,
                "time": time_value,
                "file": name,
                "source": os.path.basename(path),
            }
        )

    pvd = os.path.join(args.output_dir, "series.pvd")
    vis = os.path.join(args.output_dir, "series.visit")
    write_pvd(pvd, entries)
    write_visit_index(vis, entries)

    manifest = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "paraview_version": getattr(paraview, "__version__", None),
        "source_dir": os.path.basename(args.source_dir),
        "time_step": args.time_step,
        "cycle_step": args.cycle_step,
        "pvd_index": os.path.basename(pvd),
        "visit_index": os.path.basename(vis),
        "timesteps": table,
        "note": "Times and cycles are stored in each .vtr's FieldData as TIME "
        "and CYCLE, and in the .pvd as timestep attributes. They are "
        "deliberately not equal to the file index, so that a vignette "
        "reporting timestep, cycle and time is reporting three different "
        "things.",
    }
    with open(os.path.join(args.output_dir, "manifest.json"), "w") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)

    before = sum(os.path.getsize(p) for p in source)
    after = sum(
        os.path.getsize(os.path.join(args.output_dir, name)) for _t, name in entries
    )
    log(
        "wrote {0} .vtr + series.pvd + series.visit to {1}".format(
            len(entries), args.output_dir
        )
    )
    log(
        "times {0} .. {1}, cycles {2} .. {3}".format(
            table[0]["time"],
            table[-1]["time"],
            table[0]["cycle"],
            table[-1]["cycle"],
        )
    )
    log(
        "size {0:.1f} MB -> {1:.1f} MB ({2:.0f}% of the legacy series)".format(
            before / 1048576.0, after / 1048576.0, 100.0 * after / before
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
