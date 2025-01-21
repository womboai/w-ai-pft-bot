from enum import Enum

from nodetools.configuration.configuration import RuntimeConfig, get_network_config

IMAGE_GEN_COST = 1
NFT_MINT_COST = 1


class ImageGenType(Enum):
    IMAGE_GEN = "GENERATE_IMAGE"
    IMAGE_GEN_RESPONSE = "IMAGE_RESPONSE"

class NFTMintType(Enum):
    NFT_MINT = "NFT_MINT"
    NFT_MINT_RESPONSE = "NFT_MINT_RESPONSE"

def get_image_node_address() -> str:
    return "r3YzYAiteFiA66fC3rWnVKeecaGQcZhxnH" if RuntimeConfig.USE_TESTNET else "rMEQBmJZ8e6fFGsPpqbhGNC3v4JvptojA4" 

def get_nft_node_address() -> str:
    return "rsxZ6LMeCCvkbgSzJBCa5vHucmVqm1nyHx" if RuntimeConfig.USE_TESTNET else "rawQ8tEPb7EvAgQHDMRQGVEuq8r4QnjY8C" 



def get_https_url() -> str:
    network_config = get_network_config()
    https_url = (
        network_config.local_rpc_url
        if RuntimeConfig.HAS_LOCAL_NODE and network_config.local_rpc_url is not None
        else network_config.public_rpc_url
    )

    return https_url
