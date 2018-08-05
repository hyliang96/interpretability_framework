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

router.get('/', function (req, res) {
    parmType = req.query.type;

    const options = {
        method: 'GET',
        uri: fn.getDatasetsAllUrl(config)
    };

    request(options)
        .then(function (response) {
            // Success
            let result = JSON.parse(response);

            if (parmType != "json") {
                let jsPage = {
                    "title": "Datasets - all",
                    "datasets": result,
                    "parameters": {
                        "type": parmType
                    }
                };

                res.render("dataset-list", jsPage);
            } else {
                res.json(result);
            }
        })
        .catch(function (err) {
            // Error
            console.log(err);
            return res.sendStatus(500);
        })
});

module.exports = router;
