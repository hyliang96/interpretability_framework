import os
import sys

def get_dir_path(dir_name):
    base_path = os.getcwd().split("/")
    while base_path[-1] != str(dir_name):
        base_path = base_path[:-1]
    return "/".join(base_path) + "/"

models_path = os.path.join(get_dir_path("p5_afm_2018_demo"),"models")
folders = os.listdir(models_path)
for folder in folders:
    folder_path = os.path.join(models_path, folder)
    if os.path.isdir(folder_path) and not folder_path in sys.path:
        sys.path.append(folder_path)

import numpy as np
import tensorflow as tf
import random
import keras.losses as losses
import keras.applications.vgg19 as vgg19
import keras.backend as K

class ConvSVM(object):
    """
    A linear SVM using features extracted from the convolutional layers of a 
    pre-trained Convolutional NN.
    The dimensions of the input images, the number of channels in the input 
    images (grayscale or RGB) and the directory in which the model is found 
    must be specified beforehand
    The model currently uses architecture from keras.applications models for feature description
    """
    
    def __init__(self, model_input_dim_height, model_input_dim_width, model_input_channels, n_classes, model_dir,
                 additional_args={}):
        super(ConvSVM, self).__init__()
        if n_classes != 2:
            raise ValueError("This implementation of SVM only works with 2-class classification")
        self.n_classes = n_classes
        self.checkpoint_path = model_dir

        self.sess = tf.Session()
        self.model_input_dim_width = model_input_dim_width
        self.model_input_dim_height = model_input_dim_height
        self.model_input_channels = model_input_channels
        model_input_dim = [model_input_dim_width, model_input_dim_height , model_input_channels]
        if "learning_rate" in additional_args:
            self.learning_rate = additional_args["learning_rate"]
        else:
            print("No learning rate specified in additional_args\nUsing default value of 0.001")
            self.learning_rate = 0.001
            
        self.optim = tf.train.GradientDescentOptimizer(self.learning_rate)
        
#        alpha is a term used when calculating the loss to weight the influence
#        of model weight distances on the total loss
        if "alpha" in additional_args:
            self.alpha = additional_args["alpha"]
        else:
            self.alpha = 0.000001

#        initialise model placeholders and variables
        self.input_ = tf.placeholder(
                tf.float32,
                shape = [None] + list(model_input_dim),
                name = "in_"
        )

        
#        the feature descriptor object uses a conv net to transform images 
#        into feature space
#         self.feature_desc = FeatureDescriptor(model_input_dim, input_tensor=self.input_ )

#        get a graph op representing the feature description
#         self.feature_vec = self.feature_desc.get_descriptor_op()

        K.set_session(self.sess)
        # self.descriptor = FeatureDescriptor(model_input_dim,input_tensor = self.input_, architecture = 'vgg16', weights = 'pretrained', pooling = 'max')
        # self.conv_model = self.descriptor.get_premade_model()
        self.conv_model = vgg19.VGG19(input_tensor=self.input_, include_top=False, weights='imagenet', pooling='avg')
        for layer in self.conv_model.layers:
            layer.trainable = False

        self.feature_vec = self.conv_model.output

        n_features = self.feature_vec.get_shape().as_list()[1]

        self.labels_ = tf.placeholder(
            name="lbl_",
            shape=[None,2],
            dtype=tf.float32
        )

        self.W = tf.Variable(
            tf.random_normal(
                shape=[n_features, 1]
            ),
            name="W"
        )
        self.b = tf.Variable(
            tf.random_normal(
                shape=[1, 1]
            ),
            name="b"
        )

        self.sess.run(tf.variables_initializer(var_list=[self.W, self.b]))

        self.y = tf.argmax(self.labels_,1)
        self.y = self.y * -2
        self.y = self.y + 1
        self.y = tf.reshape(tf.cast(self.y, tf.float32),[-1,1])


#        the tensorflow saver object used for model checkpointing
        self.saver = tf.train.Saver()
        self.output = self.Output()
        self.loss = self.Loss()
        # self.loss = losses.categorical_crossentropy(self.y, self.output)
        

    def Output(self):
        """
        Returns the 'logits' of the SVM model, such that when parsed these return
        a label
        Defined as:
            y_guess = Wx + b
        """
        mdl_out = tf.subtract(
            tf.matmul(
                self.feature_vec,
                self.W
            ),
            self.b
        )
        return mdl_out


    def GetPredictions(self):
        """
        Formats the outputs of the model into a label/list of labels denoting
        what class the model 'believes' the function belongs to
        """
        return tf.sign(self.output)

    def Loss(self):
        """
        Returns the graph operation used to calculate the loss of the model at 
        a sample
        Defined as
        max(0,1-(Wx+b)(y_actual)) + aSUM(W)
        a is a regularisation term used to realise preference between accuracy
        and generality or robustness
        """
        l2_norm = tf.reduce_sum(self.W)
        classif_term = tf.reduce_mean(
            tf.maximum(
                0.,
                tf.subtract(
                    1.,
                    tf.multiply(
                        self.output,
                        self.y
                    )
                )
            )
        )
        loss = tf.add(
            classif_term,
            tf.multiply(
                self.alpha,
                l2_norm
            )
        )
        return loss

    def GetLoss(self, x, y):
        """
        Returns a value for the models loss at a point y
        """
        sample_loss = self.loss
        feed_dict = {
                self.input_ : x,
                self.labels_: y
        }
        self.LoadModel(None,self.sess)
        return self.sess.run(sample_loss, feed_dict)
    
    def GetSmoothHinge(self, t):
        """
        Returns the loss op of a differentiable close approximation of the SVMs
        loss function. The hinge loss function at a point is not differentiable by
        standard means
        However a differentiable approximation can be defined that approaches 
        Hinge Loss as a parameter t approaches 0.
        
        """
        if t == 0:
            return self.loss
        else:
            s = tf.multiply(self.output,self.y)
            exp = -(s-1)/t
            max_elem = tf.maximum(exp, tf.zeros_like(exp))
            
            log_loss = t * (max_elem + tf.log(tf.exp(exp - max_elem)  + tf.exp(tf.zeros_like(exp) - max_elem)))
            
            return log_loss
        
    def GetGradLoss(self, t = 0.0001):
        """
        Returns the gradient of the loss function wrt to the model weights.
        For SVMs this is not possible so instead the Smooth Hinge loss function
        is used as an approximation
        As t tends to 0, SmoothHinge tends to Hinge
        """
        return tf.gradients(self.GetSmoothHinge(t), self.GetWeights())
    
    def _get_batches(self, x, y, batch_size):
        """
        Randomly samples feature vectors from a distribution
        to return a batch
        """
        idcs = random.sample(range(x.shape[0]),batch_size)
        return x[idcs], y[idcs]

    def TrainModel(self, train_x, train_y, batch_size, n_steps,val_x= None, val_y=None):
        """
        Uses GD to optimise the models loss on evaluation data
        """
        # if val_x is not None:
        #     n_steps = 5 * train_x.shape[0] // batch_size
        for i in range(n_steps):
            print("training step: "+str(i))
#            get a randomly sampled batch of training data
            x, y = self._get_batches(train_x, train_y, batch_size)
            self.sess.run(
#                    train to reduce loss
                self.optim.minimize(self.loss),
                feed_dict={
                    self.input_: x,
                    self.labels_: y
                }
            )
            if val_x is not None:
                if i % 10 == 0 and i != 0:
                    loss, acc = self.EvaluateModel(val_x, val_y, batch_size)
                    print("Validation loss: "+str(loss)+"\n"+"Validation accuracy: "+str(acc))
        self.SaveModel(None,self.sess)


    def EvaluateModel(self, val_x, val_y, batch_size):
        """
        By evaluating the loss at unseen data we define a metric for the 
        effectiveness of the training, and therefore the models effectiveness
        for classification
        Accuracy is defined as:
            SUM(Wx+b && y_actual)/n_samples
        """

#        Define the graph operation for accuracy
        acc = tf.reduce_mean(
            tf.cast(
                tf.equal(
                    self.GetPredictions(),
                    self.y
                ),
                tf.float32
            )
        )

#        Load in the model weights
#         self.LoadModel(self.sess)
        accuracies = []
        losses = []

        for i in range(val_y.shape[0]//batch_size):
#            Get the accuracy of each batch of evaluation data
            x, y = self._get_batches(val_x, val_y, batch_size)
            accuracies.append(
                self.sess.run(
                    acc,
                    feed_dict={
                        self.input_: x,
                        self.labels_: y
                    }
                )
            )
            losses.append(
                self.sess.run(
                    self.loss,
                    feed_dict ={
                        self.input_: x,
                        self.labels_: y
                    }
                )
            )
#        Return mean accuracy on evaluation data
        return [np.mean(losses),np.mean(accuracies)]

    def Predict(self, predict_x, return_prediction_scores = False):
        """
        Return the model output when given a set of unseen samples as input,
        formatted to denote the models estimate for the actual class of each
        of those samples
        """
        
#        If the input is not in the format (Idx, X, Y, N_channels) format it to
#        be such
        if len(predict_x.shape) < 4:
            predict_x = np.expand_dims(predict_x, axis=0)

#        Define the graph operation that predicts the class of each point
        predictions = self.GetPredictions()
        
#        Load in the model weights
#         self.LoadModel(self.sess)
#        Find the models prediction at each sample point
        predictions = self.sess.run(
            predictions,
            feed_dict={
                self.input_: predict_x
            }
        )
        
#        One hot encode the model for use with Explanations
        prediction_scores = predictions[:]
        predictions[predictions == 1] = 0
        predictions *= -1
        one_hot = []
        for y in predictions:
            if y == 0:
                 one_hot.append([1,0])
            else:
                 one_hot.append([0,1])

        if(return_prediction_scores):
            return np.asarray(one_hot), prediction_scores
        else:
            return np.asarray(one_hot)

    def SaveModel(self,model_dir=None, sess=None):
        if sess == None:
            sess = self.sess
        if model_dir == None:
            model_dir = self.checkpoint_path
        self.saver.save(sess, os.path.join(model_dir,"model.ckpt"))

    def LoadModel(self, model_dir = None, sess=None):
        if sess == None:
            sess = self.sess
        if model_dir == None:
            model_dir = self.checkpoint_path
        self.saver.restore(sess, os.path.join(model_dir,"model.ckpt"))

    def GetWeights(self):
        """
        Returns the weights of the SVM
        """
        
#        Influence functions only needs SVM weights as Feature Descriptor are 
#        pre-determined and do not affect the loss of one point differently to
#        another
        self.LoadModel(None,self.sess)
        
        return [self.W]
    
    def GetPlaceholders(self):
        """
        Returns placeholders used by model for use with explanation techniques,
        notably for calculating the gradient of the loss
        """
        return self.input_, self.labels_



"""
The code below demonstrates the model being trained, and then tested using a 
dataset of two classes of image, those containing people wielding guns, vs.
those containing people not wielding guns
"""
if __name__ == '__main__':
    n_classes = 2
    additional_args = {
        'learning_rate': 0.01,
        'alpha': 0.0001
    }
    batch_size = 10

    from PIL import Image as Pimage
    from tqdm import tqdm


    datadir = "/home/c1435690/Projects/DAIS-ITA/Development/p5_afm_2018_demo" + "/datasets/dataset_images/resized_wielder_non-wielder/"
    contents = os.listdir(datadir)
    classes = [each for each in contents if os.path.isdir(datadir + each)]

    labels, batch = [], []
    images = []

    for each in tqdm(classes):
        print("Starting {} images".format(each))
        class_path = datadir + each
        files = os.listdir(class_path)
        for ii, file in enumerate(files, 1):
            img = Pimage.open(os.path.join(class_path, file))
            img = np.array(img)
            batch.append(img)
            labels.append(each)

    images = np.asarray(batch)

    from sklearn import preprocessing

    lb = preprocessing.LabelBinarizer()
    lb.fit(labels)

    labels_vecs = lb.transform(labels)
    labels_vecs[labels_vecs == 0] -= 1

    from sklearn.model_selection import StratifiedShuffleSplit

    ss = StratifiedShuffleSplit(n_splits=1, test_size=0.2)
    splitter = ss.split(np.zeros(labels_vecs.shape[0]), labels_vecs)

    train_idx, val_idx = next(splitter)

    half_val_len = int(len(val_idx) / 2)
    val_idx, test_idx = val_idx[:half_val_len], val_idx[half_val_len:]


    train_x, train_y = images[train_idx], labels_vecs[train_idx]
    val_x, val_y = images[val_idx], labels_vecs[val_idx]
    test_x, test_y = images[test_idx], labels_vecs[test_idx]

    input_dim = train_x[0].shape
    n_batches = 10

    svm_model = ConvSVM(
        input_dim[0],
        input_dim[1],
        input_dim[2],
        n_classes,
        os.path.join(models_path,"svm"),
        additional_args
    )
    
    print("Train shapes (x,y):", train_x.shape, train_y.shape)
    print("Validation shapes (x,y):", val_x.shape, val_y.shape)
    print("Test shapes (x,y):", test_x.shape, test_y.shape)


    for step in range(10, 200+1, 10):
        print("")
        print("training")
        print("step:", step)
        svm_model.TrainModel(train_x, train_y, batch_size, 50)
        print("")
        acc, loss = svm_model.EvaluateModel(val_x, val_y, batch_size)
        print("evaluation accuracy:")
        print(acc)
        print("evaluation loss:")
        print(loss)
        print("")

    test_y[test_y==1]=0
    test_y *= -1
    print(test_y == svm_model.Predict(test_x))
