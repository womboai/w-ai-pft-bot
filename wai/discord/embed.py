from wai.config import IMAGE_GEN_COST, NFT_MINT_COST


INFO_EMBED_FIELDS = [{
        "name": "Generate Image",
        "value": f"Generate an image using {IMAGE_GEN_COST} PFT",
        "inline": False
}, {
        "name": "Mint NFT",
        "value": f"Mint an NFT using {NFT_MINT_COST} pft",
        "inline": False 
}, {
        "name": "Accept NFT",
        "value": "Accept an NFT offer using an offer ID",
        "inline": False 
}]
