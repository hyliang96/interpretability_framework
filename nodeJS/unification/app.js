// *******************************************************************************
// * (C) Copyright IBM Corporation 2018
// * All Rights Reserved
// *******************************************************************************

var createError = require('http-errors');
var express = require('express');
var path = require('path');
var cookieParser = require('cookie-parser');
var logger = require('morgan');

var indexRouter = require('./routes/index');
var dsaRouter = require('./routes/datasets-all');
var dsdRouter = require('./routes/dataset-details');
var dstRouter = require('./routes/datasets-test-image');
var duRouter = require('./routes/dataset-use');
var maRouter = require('./routes/models-all');
var mdRouter = require('./routes/model-details');
var mfdRouter = require('./routes/models-for-dataset');
var muRouter = require('./routes/model-use');
var mpRouter = require('./routes/models-predict');
var xaRouter = require('./routes/explanations-all');
var xdRouter = require('./routes/explanation-details');
var xffRouter = require('./routes/explanations-for-filter');
var xxRouter = require('./routes/explanations-explain');
var xuRouter = require('./routes/explanation-use');

var app = express();

// view engine setup
app.set('views', path.join(__dirname, 'views'));
app.set('view engine', 'pug');

app.use(logger('dev'));
app.use(express.json());
app.use(express.urlencoded({ extended: false }));
app.use(cookieParser());
app.use(express.static(path.join(__dirname, 'public')));

//app.use(session({ secret: 'keyboard cat', cookie: { maxAge: 60000 }}))

app.use('/', indexRouter);
app.use('/datasets-all', dsaRouter);
app.use('/dataset-details', dsdRouter);
app.use('/datasets-test-image', dstRouter);
app.use('/dataset-use', duRouter);
app.use('/models-all', maRouter);
app.use('/model-details', mdRouter);
app.use('/models-for-dataset', mfdRouter);
app.use('/models-predict', mpRouter);
app.use('/model-use', muRouter);
app.use('/explanations-all', xaRouter);
app.use('/explanation-details', xdRouter);
app.use('/explanations-for-filter', xffRouter);
app.use('/explanation-use', xuRouter);
app.use('/explanations-explain', xxRouter);

// catch 404 and forward to error handler
app.use(function(req, res, next) {
  next(createError(404));
});

// error handler
app.use(function(err, req, res, next) {
  // set locals, only providing error in development
  res.locals.message = err.message;
  res.locals.error = req.app.get('env') === 'development' ? err : {};

  // render the error page
  res.status(err.status || 500);
  res.render('error');
});

module.exports = app;
