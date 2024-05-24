import os
import sys

from metaflow.decorators import StepDecorator
from metaflow.exception import MetaflowException
from metaflow.metadata import MetaDatum
from metaflow.metadata.util import sync_local_metadata_to_datastore
from metaflow.metaflow_config import (
    DATASTORE_LOCAL_DIR,
)


from .armada import ArmadaException


class ArmadaDecorator(StepDecorator):
    name = "armada"
    package_url = None
    package_sha = None

    def __init__(self, attributes=None, statically_defined=False):
        super(ArmadaDecorator, self).__init__(attributes, statically_defined)

    def step_init(self, flow, graph, step, decos, environment, flow_datastore, logger):
        # TODO: What datastore are we going to use? It can't be local...
        # TODO: Will datastores work without additional armada-specific configuration?
        if flow_datastore.TYPE not in ("s3", "azure", "gs"):
            # FIXME: Actually raise
            #             raise ArmadaException(
            #                 "The *@armada* decorator requires --datastore=s3 or "
            #                 "--datastore=azure or --datastore=gs at the moment."
            #             )
            pass

        # Set internal state.
        self.logger = logger
        self.environment = environment
        self.step = step
        self.flow_datastore = flow_datastore

        if any([deco.name == "batch" or deco.name == "kubernetes" for deco in decos]):
            raise MetaflowException(
                "Step *{step}* is marked for execution on Armada and on another "
                "remote compuer provider. Please only use one.".format(step=step)
            )

        for deco in decos:
            if getattr(deco, "IS_PARALLEL", False):
                raise ArmadaException(
                    "@kubernetes does not support parallel execution currently."
                )

    def runtime_init(self, flow, graph, package, run_id):
        # Set some more internal state.
        self.flow = flow
        self.graph = graph
        self.package = package
        self.run_id = run_id

    def runtime_task_created(
        self, task_datastore, task_id, split_index, input_paths, is_cloned, ubf_context
    ):
        if not is_cloned:
            print("runtime_task_created!")
            self._save_package_once(self.flow_datastore, self.package)

    def runtime_step_cli(
        self, cli_args, retry_count, max_user_code_retries, ubf_context
    ):
        if retry_count <= max_user_code_retries:
            # after all attempts to run the user code have failed, we don't need
            # to execute on Armada anymore. We can execute possible fallback
            # code locally.
            # FIXME: Fix this to run the armada CLI step properly.
            cli_args.commands = ["armada", "step"]
            cli_args.command_args.append(self.package_sha)
            cli_args.command_args.append(self.package_url)
            # FIXME: Hard-coded for now:
            cli_args.command_args.append("test")
            cli_args.command_args.append("job-set-alpha")
            cli_args.command_args.append("job-file.dummy")
            attributes = {
                "host": "localhost",
                "port": "50051",
            }

            cli_args.command_options.update(attributes)
            # cli_args.command_options = attributes
            cli_args.entrypoint[0] = sys.executable
            print(cli_args)

    def task_pre_step(
        self,
        step_name,
        task_datastore,
        metadata,
        run_id,
        task_id,
        flow,
        graph,
        retry_count,
        max_retries,
        ubf_context,
        inputs,
    ):
        print("armada_decorator.py: task_pre_step!")
        self.metadata = metadata
        self.task_datastore = task_datastore

        meta = {}
        # meta["armada-job-id"] = os.environ["METAFLOW_ARMADA_JOB_ID"]
        entries = [
            MetaDatum(
                field=k, value=v, type=k, tags=["attempt_id:{0}".format(retry_count)]
            )
            for k, v in meta.items()
        ]

        # Register book-keeping metadata for debugging.
        print("armada_decorator.py: metadata.register_metadata!")
        self.metadata.register_metadata(run_id, step_name, task_id, entries)
        # FIXME: Do we need to predicate this on an environment variable being set?
        # if "METAFLOW_ARMADA_WORKLOAD" in os.environ:
        # FIXME: Modify these to match any information we get from Armada.
        #         meta = {}
        #         meta["ARMADA-pod-name"] = os.environ["METAFLOW_ARMADA_POD_NAME"]
        #         meta["ARMADA-pod-namespace"] = os.environ["METAFLOW_ARMADA_POD_NAMESPACE"]
        #         meta["ARMADA-pod-id"] = os.environ["METAFLOW_ARMADA_POD_ID"]
        #         meta["ARMADA-pod-service-account-name"] = os.environ[
        #             "METAFLOW_ARMADA_SERVICE_ACCOUNT_NAME"
        #         ]
        #         meta["ARMADA-node-ip"] = os.environ["METAFLOW_ARMADA_NODE_IP"]
        #
        #         # FIXME: Need a way to fetch Armada metadata
        #         # if ARMADA_FETCH_EC2_METADATA:
        #         #    instance_meta = get_ec2_instance_metadata()
        #         #    meta.update(instance_meta)
        #
        #         entries = [
        #             MetaDatum(field=k, value=v, type=k, tags=[])
        #             for k, v in meta.items()
        #             if v is not None
        #         ]
        #         # Register book-keeping metadata for debugging.
        #         print("armada_decorator.py: task_pre_step: register_metadata")
        #         metadata.register_metadata(run_id, step_name, task_id, entries)

        # Start MFLog sidecar to collect task logs.
        # FIXME: # Do we need an Armada log sidecar?
        # self._save_logs_sidecar = Sidecar("save_logs_periodically")
        # self._save_logs_sidecar.start()

    def task_finished(
        self, step_name, flow, graph, is_task_ok, retry_count, max_retries
    ):
        # task_finished may run locally if fallback is activated for @catch
        # decorator.
        if "METAFLOW_ARMADA_WORKLOAD" in os.environ:
            # If `local` metadata is configured, we would need to copy task
            # execution metadata from the Armada container to user's
            # local file system after the user code has finished execution.
            # This happens via datastore as a communication bridge.

            # TODO:  There is no guarantee that task_prestep executes before
            #        task_finished is invoked. That will result in AttributeError:
            #        'KubernetesDecorator' object has no attribute 'metadata' error.
            if self.metadata.TYPE == "local":
                print("task_finished")
                # Note that the datastore is *always* Amazon S3 (see
                # runtime_task_created function).
                sync_local_metadata_to_datastore(
                    DATASTORE_LOCAL_DIR, self.task_datastore
                )

        try:
            self._save_logs_sidecar.terminate()
        except:
            # Best effort kill
            pass

        pass

    @classmethod
    def _save_package_once(cls, flow_datastore, package):
        if cls.package_url is None:
            print("_save_package_once in the house!")
            cls.package_url, cls.package_sha = flow_datastore.save_data(
                [package.blob], len_hint=1
            )[0]
