# Armada Metaflow Plugin/Decorator HOW-TO

## Introduction
This document explains how to setup, run, and test the `@armada` metaflow decorator. Decorating a metaflow step with `@armada` 
causes that step to be executed as an [Armada](https://github.com/armadaproject/armada) job.

## Setting up a Local Sandbox
You'll need a few components deployed and running either locally, or somewhere accessible via your network in order to
start using and testing the `@armada` Metaflow decorator.

### Armada
A fully operational Armada instance can be quickly booted on a local machine by cloning the 
[Armada repository](https://github.com/armadaproject/armada):

```bash
$ git clone https://github.com/armadaproject/armada
```
and then following the [Developer Guide](https://github.com/armadaproject/armada/blob/master/docs/developer.md).

Once you have Armada's requirements satisfied, you can run:

```bash
$ mage localDev full
```
from Armada's repository root. This will cause all Armada services and necessary dependencies to be booted and 
deployed via `docker compose` and [`kind`](https://kind.sigs.k8s.io/).

>[!TIP]
>You will need an Armada queue available in order to run metaflow `@armada` steps. You can create one by running:
>```bash
>$ ~/go/src/github.com/armadaproject/armada/bin/armadactl create queue metaflow
>```
>once Armada is built and running.


### Localstack 
[Localstack](https://www.localstack.cloud/) is necessary to provide an S3 service so that flow steps may store and 
retrieve data. If you have an S3 compatible service already available you may skip setting up localstack and use 
that instead.

A localstack instance can be booted by following their 
[installation guide](https://docs.localstack.cloud/getting-started/installation/) and then running:

```bash
$ localstack --profile=all_networks start -d
```
This will start a localstack container running an S3 compatible service (amongst others).

>[!TIP]
>You may want localstack to listen on `0.0.0.0` in order to expose it on a network that flows may reach from 'outside' 
>of Armada as well has jobs launched 'inside' Armada. You will need a file at `~/.localstack/all_networks.env` with the
>following contents:
>```env
>GATEWAY_LISTEN=0.0.0.0:4566
>```
>Which will cause localstack to listen on port `4566` on all interfaces. This is why we added `--profile=all_networks` as an
>option to the invocation of `localstack`.

See [Localstack's Configuration docs](https://docs.localstack.cloud/references/configuration/) for more information.

To create a bucket for use by metaflow you may run:
```shell
$ awslocal s3 mb s3://localstack-metaflow-armada
```

### Metaflow
In order to use the `@armada` Metaflow decorator/plugin you will need to clone [G-Research's fork](https://github.com/G-Research/metaflow) of the metaflow repository:
```bash
$ git clone https://github.com/G-Research/metaflow
```
Metaflow must be configured to enable the armada decorator, below is an example Metaflow configuration file:

```json
{
    "METAFLOW_DEBUG_EXT": true,
    "METAFLOW_CONSOLE_TRACE_ENABLED": true,
    "METAFLOW_ENABLED_CLI": ["armada"],
    "METAFLOW_ENABLED_STEP_DECORATOR": ["armada"],
    "METAFLOW_S3_ENDPOINT_URL": "http://my.s3service.url:4566",
    "METAFLOW_DEFAULT_DATASTORE": "s3",
    "METAFLOW_DATASTORE_SYSROOT_S3": "s3://localstack-metaflow-armada",
}   
```
Which is typically located at `~/.metaflowconfig/config.json`. This enables the `@armada` step decorator, as well as cli, and points metaflow to our s3 service. Additionally, the configuration above enables some additional debug and tracing output. Replace `http://my.s3service.url:4566` with an appropriate url to reach your desired s3 service.

## The @armada Decorator

The `@armada` decorator is relatively simple and straight-forward in purpose: The `@step` method within a Metaflow flow 
decorated by it will be executed as a job launched by Armada. Since Armada is primarily a manager of many kubernetes 
clusters, the end result is similar to the `@kubernetes` decorator. Ultimately the step will execute inside a 
container managed by a kubernetes cluster, which in turn is managed by Armada.

### Required Arguments
Some arguments to the `@armada` decorated are required:
* `host` - The Armada host.
* `port` - The Armada port.
* `queue` - The Armada queue to which the Armada job created by this step will be submitted. Earlier in this how-to we created a queue named `metaflow`.
* `job_set_id` - A way to group related jobs within Armada. The specified job set will be created if it doesn't already exist.
### Live Logs
If you want to have live logs streamed during your flow, then you should specify the following:
* `logging_host` - The logging host, usually Armada's Binoculars service.
* `logging_port` - The logging port, usually Armada's Binoculars service.
>[!WARNING]
>Binoculars is not an officially supported external Armada API or service. It may change or disappear at any time. However
>the `JobLogClient` located in the Python `armada-client` library is meant to be a durable, externally consumable interface 
>for retrieving Armada job logs.

### Optional Arguments
* `cpu` - The requested amount of cpu resources to provide to the Armada job.
* `memory` - The requested amount of memory resource to provide to the Armada job.
* `disk` - The requested amount of disk resource to provide to the Armada job.
* `insecure_no_ssl` - Connections to Armada will not use SSL. Useful for test environments.

### Full Example `@armada` Flow

A full example of using the `@armada` step decorator within a flow is given below:

```python
from metaflow import FlowSpec, step, armada                                                                                     


class ArmadaFlow(FlowSpec):                                                                                                          """A simple flow demonstrating the use of Armada with Metaflow."""

    @step
    def start(self):                                                                                                                   """Sets a local variable."""
        print("Start")                                                                                                                 self.local_var = 214 
        print(f"Set self.local_var: {self.local_var}")
        self.next(self.submit_job_decorated) 
        
    @armada(
        host="localhost",
        port="50051",
        logging_host="localhost",
        logging_port="50053",
        queue="test",
        job_set_id="job-set-alpha",
        cpu="240m",
        memory="2Gi",
        insecure_no_ssl=True,
    )                                              
    @step
    def submit_job_decorated(self):
        """Sets a variable within Armada and demonstrates access to data
        from previous steps."""
        print("Hello world from an Armada-launched container!")
        self.armada_var = 1337                                                                                         
        print(f"armada_var: {self.armada_var} local_var: {self.local_var}")
        self.next(self.end)
        
    @step
    def end(self):
        """Ends the flow and shows that the variable set within Armada is
        available outside."""
        print(f"Armada container variable retrieved outside: {self.armada_var}")
        print(f"local_var: {self.local_var}")                                  
        print("End")


if __name__ == "__main__":                                           
    ArmadaFlow()                
```

You can run this example by saving the above to a file, say `armada.py` and running:
```bash
$ python armada.py run
```
If everything is successful you'll see output similar to the following:
```
Metaflow 2.11.16.post14+gitf228391 executing ArmadaFlow for user:clif
Validating your flow...
    The graph looks good!
Running pylint...
    Pylint is happy!
2024-10-09 11:52:02.239 Workflow starting (run-id 1728492722239186):
2024-10-09 11:52:02.319 [1728492722239186/start/1 (pid 305198)] Task is starting.
2024-10-09 11:52:02.678 [1728492722239186/start/1 (pid 305198)] Start
2024-10-09 11:52:02.763 [1728492722239186/start/1 (pid 305198)] Set self.local_var: 214
2024-10-09 11:52:02.790 [1728492722239186/start/1 (pid 305198)] Task finished successfully.
2024-10-09 11:52:02.863 [1728492722239186/submit_job_decorated/2 (pid 305223)] Task is starting.
2024-10-09 11:52:03.181 [1728492722239186/submit_job_decorated/2 (pid 305223)] Submitted job with ID: 01j9s33pybc7qtkvz191nmvhym
2024-10-09 11:52:03.192 [1728492722239186/submit_job_decorated/2 (pid 305223)] Armada job entered EventType.submitted state.
2024-10-09 11:52:03.192 [1728492722239186/submit_job_decorated/2 (pid 305223)] Armada job entered EventType.queued state.
2024-10-09 11:52:06.095 [1728492722239186/submit_job_decorated/2 (pid 305223)] Armada job entered EventType.leased state.
2024-10-09 11:52:12.517 [1728492722239186/submit_job_decorated/2 (pid 305223)] Armada job entered EventType.pending state.
2024-10-09 11:52:14.523 [1728492722239186/submit_job_decorated/2 (pid 305223)] Armada job entered EventType.running state.
2024-10-09 11:52:14.524 [1728492722239186/submit_job_decorated/2 (pid 305223)] Log begins for job '01j9s33pybc7qtkvz191nmvhym'
2024-10-09 11:52:27.588 [1728492722239186/submit_job_decorated/2 (pid 305223)] 2024-10-09T16:52:27.498308916Z init script
2024-10-09 11:52:53.680 [1728492722239186/submit_job_decorated/2 (pid 305223)] 2024-10-09T16:52:27.502461975Z Setting up task environment.
2024-10-09 11:52:53.681 [1728492722239186/submit_job_decorated/2 (pid 305223)] 2024-10-09T16:52:53.382369842Z Downloading code package...
2024-10-09 11:52:55.688 [1728492722239186/submit_job_decorated/2 (pid 305223)] 2024-10-09T16:52:55.181292992Z Code package downloaded.
2024-10-09 11:52:55.688 [1728492722239186/submit_job_decorated/2 (pid 305223)] 2024-10-09T16:52:55.479651256Z Task is starting.
2024-10-09 11:52:57.696 [1728492722239186/submit_job_decorated/2 (pid 305223)] 2024-10-09T16:52:57.481993499Z Collecting armada_client==0.3.0
2024-10-09 11:52:57.696 [1728492722239186/submit_job_decorated/2 (pid 305223)] 2024-10-09T16:52:57.555397611Z   Downloading armada_client-0.3.0-py3-none-any.whl.metadata (2.4 kB)
2024-10-09 11:53:00.708 [1728492722239186/submit_job_decorated/2 (pid 305223)] 2024-10-09T16:53:00.087575581Z Collecting grpcio>=1.46.3 (from armada_client==0.3.0)
2024-10-09 11:53:00.708 [1728492722239186/submit_job_decorated/2 (pid 305223)] 2024-10-09T16:53:00.093348178Z   Downloading grpcio-1.66.2-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl.metadata (3.9 kB)
2024-10-09 11:53:02.715 [1728492722239186/submit_job_decorated/2 (pid 305223)] 2024-10-09T16:53:01.994215068Z Collecting grpcio-tools>=1.46.3 (from armada_client==0.3.0)
2024-10-09 11:53:02.715 [1728492722239186/submit_job_decorated/2 (pid 305223)] 2024-10-09T16:53:02.046622187Z   Downloading grpcio_tools-1.66.2-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl.metadata (5.3 kB)
2024-10-09 11:53:03.719 [1728492722239186/submit_job_decorated/2 (pid 305223)] 2024-10-09T16:53:02.093725416Z Collecting mypy-protobuf>=3.2.0 (from armada_client==0.3.0)
2024-10-09 11:53:03.719 [1728492722239186/submit_job_decorated/2 (pid 305223)] 2024-10-09T16:53:02.099605762Z   Downloading mypy_protobuf-3.6.0-py3-none-any.whl.metadata (466 bytes)
2024-10-09 11:53:03.719 [1728492722239186/submit_job_decorated/2 (pid 305223)] 2024-10-09T16:53:02.993751481Z Collecting protobuf>=3.20.3 (from armada_client==0.3.0)
2024-10-09 11:53:04.723 [1728492722239186/submit_job_decorated/2 (pid 305223)] 2024-10-09T16:53:02.999923525Z   Downloading protobuf-5.28.2-cp38-abi3-manylinux2014_x86_64.whl.metadata (592 bytes)
2024-10-09 11:53:04.724 [1728492722239186/submit_job_decorated/2 (pid 305223)] 2024-10-09T16:53:03.742900143Z Collecting setuptools (from grpcio-tools>=1.46.3->armada_client==0.3.0)
2024-10-09 11:53:04.724 [1728492722239186/submit_job_decorated/2 (pid 305223)] 2024-10-09T16:53:03.748465711Z   Downloading setuptools-75.1.0-py3-none-any.whl.metadata (6.9 kB)
2024-10-09 11:53:04.724 [1728492722239186/submit_job_decorated/2 (pid 305223)] 2024-10-09T16:53:03.892486327Z Collecting types-protobuf>=4.24 (from mypy-protobuf>=3.2.0->armada_client==0.3.0)
2024-10-09 11:53:04.724 [1728492722239186/submit_job_decorated/2 (pid 305223)] 2024-10-09T16:53:03.897514789Z   Downloading types_protobuf-5.28.0.20240924-py3-none-any.whl.metadata (2.1 kB)
2024-10-09 11:53:04.724 [1728492722239186/submit_job_decorated/2 (pid 305223)] 2024-10-09T16:53:03.946246986Z Downloading armada_client-0.3.0-py3-none-any.whl (190 kB)
2024-10-09 11:53:04.724 [1728492722239186/submit_job_decorated/2 (pid 305223)] 2024-10-09T16:53:03.982254817Z Downloading grpcio-1.66.2-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (5.8 MB)
2024-10-09 11:53:04.724 [1728492722239186/submit_job_decorated/2 (pid 305223)] 2024-10-09T16:53:04.131303885Z    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 5.8/5.8 MB 38.8 MB/s eta 0:00:00
2024-10-09 11:53:04.724 [1728492722239186/submit_job_decorated/2 (pid 305223)] 2024-10-09T16:53:04.136596116Z Downloading grpcio_tools-1.66.2-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (2.4 MB)
2024-10-09 11:53:04.725 [1728492722239186/submit_job_decorated/2 (pid 305223)] 2024-10-09T16:53:04.188201851Z    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 2.4/2.4 MB 47.7 MB/s eta 0:00:00
2024-10-09 11:53:04.725 [1728492722239186/submit_job_decorated/2 (pid 305223)] 2024-10-09T16:53:04.194602953Z Downloading mypy_protobuf-3.6.0-py3-none-any.whl (16 kB)
2024-10-09 11:53:08.822 [1728492722239186/submit_job_decorated/2 (pid 305223)] 2024-10-09T16:53:04.214971371Z Downloading protobuf-5.28.2-cp38-abi3-manylinux2014_x86_64.whl (316 kB)
2024-10-09 11:53:08.823 [1728492722239186/submit_job_decorated/2 (pid 305223)] 2024-10-09T16:53:04.237846991Z Downloading types_protobuf-5.28.0.20240924-py3-none-any.whl (68 kB)
2024-10-09 11:53:08.823 [1728492722239186/submit_job_decorated/2 (pid 305223)] 2024-10-09T16:53:04.256961208Z Downloading setuptools-75.1.0-py3-none-any.whl (1.2 MB)
2024-10-09 11:53:08.823 [1728492722239186/submit_job_decorated/2 (pid 305223)] 2024-10-09T16:53:04.286439138Z    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 1.2/1.2 MB 38.5 MB/s eta 0:00:00
2024-10-09 11:53:08.823 [1728492722239186/submit_job_decorated/2 (pid 305223)] 2024-10-09T16:53:04.441925058Z Installing collected packages: types-protobuf, setuptools, protobuf, grpcio, mypy-protobuf, grpcio-tools, armada_client
2024-10-09 11:53:08.823 [1728492722239186/submit_job_decorated/2 (pid 305223)] 2024-10-09T16:53:08.280217685Z Successfully installed armada_client-0.3.0 grpcio-1.66.2 grpcio-tools-1.66.2 mypy-protobuf-3.6.0 protobuf-5.28.2 setuptools-75.1.0 types-protobuf-5.28.0.20240924
2024-10-09 11:53:14.850 [1728492722239186/submit_job_decorated/2 (pid 305223)] 2024-10-09T16:53:08.280441813Z WARNING: Running pip as the 'root' user can result in broken permissions and conflicting behaviour with the system package manager, possibly rendering your system unusable.It is recommended to use a virtual environment instead: https://pip.pypa.io/warnings/venv. Use the --root-user-action option if you know what you are doing and want to suppress this warning.
2024-10-09 11:53:14.850 [1728492722239186/submit_job_decorated/2 (pid 305223)] 2024-10-09T16:53:14.044112576Z Hello world from an Armada-launched container!
2024-10-09 11:53:21.115 [1728492722239186/submit_job_decorated/2 (pid 305223)] 2024-10-09T16:53:14.048352225Z armada_var: 1337 local_var: 214
2024-10-09 11:53:21.115 [1728492722239186/submit_job_decorated/2 (pid 305223)] Armada job entered EventType.succeeded state.
2024-10-09 11:53:31.899 [1728492722239186/submit_job_decorated/2 (pid 305223)] Armada job reached terminal state: job_id: "01j9s33pybc7qtkvz191nmvhym"
2024-10-09 11:53:31.899 [1728492722239186/submit_job_decorated/2 (pid 305223)] job_set_id: "job-set-alpha"
2024-10-09 11:53:31.899 [1728492722239186/submit_job_decorated/2 (pid 305223)] queue: "test"
2024-10-09 11:53:31.899 [1728492722239186/submit_job_decorated/2 (pid 305223)] created {
2024-10-09 11:53:31.899 [1728492722239186/submit_job_decorated/2 (pid 305223)] seconds: 1728492801
2024-10-09 11:53:31.899 [1728492722239186/submit_job_decorated/2 (pid 305223)] nanos: 66933627
2024-10-09 11:53:31.899 [1728492722239186/submit_job_decorated/2 (pid 305223)] }
2024-10-09 11:53:31.899 [1728492722239186/submit_job_decorated/2 (pid 305223)] 
2024-10-09 11:53:31.899 [1728492722239186/submit_job_decorated/2 (pid 305223)] Log ends for job '01j9s33pybc7qtkvz191nmvhym'
2024-10-09 11:53:31.923 [1728492722239186/submit_job_decorated/2 (pid 305223)] Task finished successfully.
2024-10-09 11:53:31.984 [1728492722239186/end/3 (pid 306569)] Task is starting.
2024-10-09 11:53:32.349 [1728492722239186/end/3 (pid 306569)] Armada container variable retrieved outside: 1337
2024-10-09 11:53:32.351 [1728492722239186/end/3 (pid 306569)] local_var: 214
2024-10-09 11:53:32.436 [1728492722239186/end/3 (pid 306569)] End
2024-10-09 11:53:32.462 [1728492722239186/end/3 (pid 306569)] Task finished successfully.
2024-10-09 11:53:32.515 Done!
```

## Still TODO
While the `@armada` decorator is functional and useful today, there are still some rough edges and improvements to be made.
* Allow use of the `@resources` decorator.
* Support storage backends other than S3.
* And more...

## Contact

Armada has a [slack channel](https://cloud-native.slack.com/archives/C03T9CBCEMC).
