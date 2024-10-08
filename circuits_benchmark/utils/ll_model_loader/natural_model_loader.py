from circuits_benchmark.utils.ll_model_loader.siit_model_loader import SIITModelLoader


class NaturalModelLoader(SIITModelLoader):
    """Natural model loader is just an SIIT model loader for weights 100."""

    def __init__(self,
                 case,
                 load_from_wandb: bool | None = False,
                 wandb_project: str | None = None,
                 wandb_name: str | None = None):
        super().__init__(
            case,
            "100",
            load_from_wandb=load_from_wandb,
            wandb_project=wandb_project,
            wandb_name=wandb_name
        )
