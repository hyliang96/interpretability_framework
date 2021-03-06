// *******************************************************************************
// * (C) Copyright IBM Corporation 2018
// * All Rights Reserved
// *******************************************************************************

let express = require('express');
let router = express.Router();
let request = require('request-promise');
let config = require('../config');
let fn = require('./functions-general');
let parmType = null;
let parmDsName = null;
let parmNumImages = null;

router.get('/', function (req, res) {
    parmType = req.query.type;
    parmDsName = req.query.dataset;
    parmNumImages = req.query.num_images;

    let numImages = parseInt(parmNumImages);

    if (!isNaN(numImages)) {
        if (parmDsName == null) {
            let errMsg = "Error: No dataset specified";
            return res.status(500).send(errMsg);
        } else {
            const options = {};

            if (parmNumImages == null) {
                options.method = "GET";
                options.uri = fn.getDatasetFixedImageListUrl(config, parmDsName);
            } else {
                options.method = "POST";
                options.uri = fn.getDatasetImageListUrl(config);
                options.body = {
                    "dataset_name": parmDsName,
                    "num_images": numImages
                },
                    options.json = true;
            }

            request(options)
                .then(function (response) {
                    // Success
                    let result = processMultipleImageJson(response);

                    if (parmType == "html") {
                        let jsPage = {
                            "title": config.unified_apis.dataset.test_images.url,
                            "images": result,
                            "parameters": {
                                "type": parmType,
                                "dataset": parmDsName,
                                "num_images": parmNumImages
                            }
                        };

                        res.render(config.unified_apis.dataset.test_images.route, jsPage);
                    } else {
                        res.json(result);
                    }
                })
                .catch(function (err) {
                    // Error
                    console.log(err);
                    return res.sendStatus(500);
                })
        }
    } else {
        let errMsg = "Error: num_images parameter is '" + parmNumImages + "' but must be a valid positive integer";
        return res.status(500).send(errMsg);
    }
});

function processMultipleImageJson(rawJs) {
    let result = [];
    let iList = rawJs.input;
    let gtList = rawJs.ground_truth;
    let inList = rawJs.image_name;

    for (let i in iList) {
        let thisImg = {};
        thisImg.input = iList[i];
        thisImg.ground_truth = gtList[i];
        thisImg.image_name = inList[i];

        result.push(thisImg);
    }

    return result;
}

module.exports = router;