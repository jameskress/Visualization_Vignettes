from paraview import catalyst
from paraview.simple import *
from paraview.catalyst import get_args, get_execute_params
import time
import os

frequency = 1

# Specify the output directory. Ideally, this should be an
# absolute path to avoid confusion.
outputDirectory = "./datasets"

# Specify extractor type to use, if any.
# e.g. for CSV, set extractorType to 'CSV'
extractorType = None

# Specify the Catalyst channel name
def create_extractor(data):
    if extractorType is not None:
        return CreateExtractor(extractorType, data, registrationName=extractorType)

    grid = data.GetClientSideObject().GetOutputDataObject(0)
    if grid.IsA("vtkImageData"):
        return CreateExtractor("VTI", data, registrationName="VTI")
    elif grid.IsA("vtkRectilinearGrid"):
        return CreateExtractor("VTR", data, registrationName="VTR")
    elif grid.IsA("vtkStructuredGrid"):
        return CreateExtractor("VTS", data, registrationName="VTS")
    elif grid.IsA("vtkPolyData"):
        return CreateExtractor("VTP", data, registrationName="VTP")
    elif grid.IsA("vtkUnstructuredGrid"):
        return CreateExtractor("VTU", data, registrationName="VTU")
    elif grid.IsA("vtkUniformGridAMR"):
        return CreateExtractor("VTH", data, registrationName="VTH")
    elif grid.IsA("vtkMultiBlockDataSet"):
        return CreateExtractor("VTM", data, registrationName="VTM")
    elif grid.IsA("vtkPartitionedDataSet"):
        return CreateExtractor("VTPD", data, registrationName="VTPD")
    elif grid.IsA("vtkPartitionedDataSetCollection"):
        return CreateExtractor("VTPC", data, registrationName="VTPC")
    elif grid.IsA("vtkHyperTreeGrid"):
        return CreateExtractor("HTG", data, registrationName="HTG")
    else:
        raise RuntimeError(
            "Unsupported data type: %s. Check that the adaptor "
            "is providing channel named %s",
            grid.GetClassName(),
            catalystChannel,
        )


# print values for parameters passed via adaptor (note these don't change,
# and hence must be created as command line params)
args = get_args()
for arg in args:
    if "channel-name" in arg:
        channel_name = arg.split("=")[1]
print("executing catalyst_pipeline")
print("===================================")
print("pipeline args={}".format(get_args()))
print("===================================")

# registrationName must match the channel name used in the 'CatalystAdaptor'.
producer = TrivialProducer(registrationName=channel_name)
producer.UpdatePipeline()

# example of how to query the pipeline to see what data we are getting
numPointArrays = producer.GetPointDataInformation().GetNumberOfArrays()
print("=======================================================")
print("The catalyst stream contains the following arrays---")
print("Number of point arrays = {}".format(numPointArrays))
for i in range(numPointArrays):
    currentArray = producer.GetPointDataInformation().GetArray(i)
    print("Array = {}, name = {}".format(i, currentArray.GetName()))
print("=======================================================")
producer.PointArrayStatus = ["v", "u"]

# create a new 'Contour'
contour1 = Contour(registrationName="Contour1", Input=producer)
contour1.ContourBy = ["POINTS", "v"]
contour1.Isosurfaces = [0.2053265338835752]
contour1.PointMergeMethod = "Uniform Binning"

# Returns extractor type based on data (or you can manually specify
extractor = create_extractor(contour1)

# ------------------------------------------------------------------------------
# Catalyst options
options = catalyst.Options()
options.ExtractsOutputDirectory = outputDirectory
options.GlobalTrigger.Frequency = frequency
options.EnableCatalystLive = 1
options.CatalystLiveTrigger = "TimeStep"

# --------------------------------------------------------------
# Dynamically determine client
clientport = 22222
clienthost = "localhost"
options.CatalystLiveURL = "localhost:22222"
if "CATALYST_CLIENT" in os.environ:
    clienthost = os.environ["CATALYST_CLIENT"]
options.CatalystLiveURL = str(clienthost) + ":" + str(clientport)


def catalyst_execute(info):
    global producer

    producer.UpdatePipeline()

    # get params as example of a parameter changing during the simulation
    params = get_execute_params()

    print("\n===================================")
    print("executing (cycle={}, time={})".format(info.cycle, info.time))
    print("-----")
    print("pipeline parameters:")
    print("\n".join(params))
    print("-----")
    print("bounds:", producer.GetDataInformation().GetBounds())
    print("v-range:", producer.PointData["v"].GetRange(-1))
    print("u-range:", producer.PointData["u"].GetRange(-1))
    print("===================================\n")
    # slow things down for live view
    time.sleep(1)


# ------------------------------------------------------------------------------
if __name__ == "__main__":
    from paraview.simple import SaveExtractsUsingCatalystOptions

    # Code for non in-situ environments; if executing in post-processing
    # i.e. non-Catalyst mode, let's generate extracts using Catalyst options
    SaveExtractsUsingCatalystOptions(options)
