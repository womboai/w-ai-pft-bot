from enum import Enum

from nodetools.configuration.configuration import RuntimeConfig

IMAGE_GEN_COST = 1
NFT_MINT_COST = 1


class ImageGenType(Enum):
    IMAGE_GEN = "GENERATE_IMAGE"
    IMAGE_GEN_RESPONSE = "IMAGE_RESPONSE"

def get_image_node_address() -> str:
    return "r3YzYAiteFiA66fC3rWnVKeecaGQcZhxnH" if RuntimeConfig.USE_TESTNET else "rMEQBmJZ8e6fFGsPpqbhGNC3v4JvptojA4" 
