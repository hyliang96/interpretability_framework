#!/usr/bin/env python3
# -*- coding: utf-8 -*-


from scipy.optimize import fmin_ncg
import numpy as np
import tensorflow as tf
from tensorflow.python.ops import array_ops

class InfluenceExplainer(object):
    def __init__(self,model, train_imgs, train_lbls):
        super(InfluenceExplainer, self).__init__()
        self.model = model
        self.sess = model.sess
        self.params, self.num_params = model.GetWeights()
        self.num_params = len(np.concatenate(self.sess.run(self.params)))
        self.input_, self.labels_ = model.GetPlaceholders()
        self.v_placeholder = [
                tf.placeholder(
                    tf.float32,
                    shape=a.get_shape()
                )
                for a in self.params
        ]
        self.grad_loss = self.model.GetGradLoss()
        self.hvp = self._get_approx_hvp(self.grad_loss, self.params, self.v_placeholder)
        self.train_imgs = train_imgs
        self.train_lbls = train_lbls
        self.vec_to_list = self._get_vec_to_list()
        self.cached_influence = {}
        
    def Explain(self, test_img, n_max=4, additional_args = {}):
        """
        Explain test image by showing the training sampels with most influence
        on the models classification of the image.
        This method uses the approximation of the Hessian as defined in 
        "Understanding Black-box Predictions via Influence Functions" by 
        Pang Wei Koh and Percy Liang.
        The method involves precomputing
        s_test = Hess_w_min^-1 x Del_w(L(z_test,w_min))
        f.a. test samples, s_test is then substituted into the Inf fn.
        By accurately approximating s_test computation is much faster without 
        much cost.
        Input:
            test_img : test image to explain
            n_max : number of train images to select for explanation, i.e.
            first n_max images from train set in order of descending 
        """
        compute = True
        if "label" in additional_args:
            label = additional_args["label"]
        else:
            label = self.model.Predict(test_img)
        cache = False
        if "cache" in additional_args:
            if test_img not in self.cached_influence:
                if n_max == len(self.cached_influence[test_img]):
                    compute = False
                else:
                    cache = True
        
        if compute:
            feed_dict = {
                self.input_:         
            }
            test_loss_gradient = self.model.GetGradLoss(test_img, label)
            s_test = self._get_approx_inv_hvp(test_loss_gradient)
            influences = []
            for train_pt in zip(self.train_imgs, self.train_lbls):
                influences.append(self._influence_on_loss_at_test_image(s_test,train_pt))
#           Get the n_max first training images in order of descending influence
            idcs = np.argsort(influences)[-n_max:]
            max_imgs = train_imgs[idcs:]
            if cache:
                self.cached_influence[test_img] = max_imgs
        else:
            max_imgs = self.cached_influence[test_img]
            
        return max_imgs
            
            
        
    def _influence_on_loss_at_test_image(self, s, train_pt):
        """
        Approximates the influence an image from the models training set has on
        the loss of the model at a test point.
        I_up_loss(z, z_test) is defined as:
            -Grad_w x Loss(z_test,w_min)^T x Hess_w_min^-1 x Grad_w x Loss(z,w_min)
        We precompute s_test equiv. to Hess_w_min^-1 x Grad_w x Loss(z_test, w_min)
        for a test point in order to save time on computations
        
        Input:
            s : the vector precomputed by _get_approx_inv_hvp
            train_pt : a 2-tuple containing the image label pair of one training
            point
        """
        
#        Get loss  Loss(z,w_min)
        feed_dict = {
                self.input_ : train_pt[0],
                self.labels_ : train_pt[1]
        }
#        Get gradient of loss at training point: Grad_w x Loss(z,w_min)
        grad_train_loss_w_min = self.grad_loss(train_pt[0], train_pt[1])
#        Calculate Influence
        influence_on_loss_at_test_image = np.dot(np.concatenate(s), np.concatenate(grad_train_loss_w_min)) / len(self.train_lbls)
        
        return influence_on_loss_at_test_image
        
    def _get_approx_inv_hvp(self, v):
        """
        Returns the value of the product of the inverse Hessian of a fn and a 
        given vector v
        This value is approximated via Newton Conjugate Gradient Descent:
        """
        
#        function to minimise
        fmin = self._get_fmin_inv_hvp(v)
#        gradient of function
        grad_fmin = self._get_grad_fmin(v)
#        hessian of function
        hess_fmin_p = self._get_fmin_hvp
#        callback function
        fmin_cg_callback = self._get_cg_callback(v)
        
        approx_inv_hvp = fmin_ncg(
            f = fmin,
            x0 = np.concatenate(v),
            fprime = grad_fmin,
            fhess_p = hess_fmin_p,
            callback = fmin_cg_callback,
            avextol = 1e-8,
            maxiter = 100
        )
        
        return self.vec_to_list(approx_inv_hvp)
        
    def _get_approx_hvp(self,grads,xs,t):
        """
        Returns the value of the product of the Hessian of a fn ys w.r.t xs,
        and a vector t
        Approximates the product using a backprop-like approach to obtain an
        implicit Hessian-vector product
        """
        
#        N.B. Need to take more time to understand this function, it's almost
#        completely parroted from Percy's implementation
        
#        Validate input shapes
        length = len(xs)
        if len(t) != length:
            raise ValueError("xs and v must have the same length")
        
#        First backprop        
        assert len(grads) == length
        
        elemwise_prods = [
#                stop gradient tells the tf graph to treat the parameter as a 
#                constant, i.e. to not factor it in to gradient computation
                tf.multiply(grad_elem, array_ops.stop_gradient(v_elem))
                for grad_elem, v_elem in zip (grads, t) if grad_elem is not None
        ]
        
#        Second backprop
        grads_w_none = tf.gradients(elemwise_prods, xs)
        
        return_grads = [
                grad_elem if grad_elem is not None else tf.zeros_like(x) \
                for x, grad_elem in zip(xs, grads_w_none)
        ]
        
        return return_grads
        
    def _get_fmin_inv_hvp(self, v):
        """
        H_w_min ^ -1 x v is equiv. to 
        argmin_t{0.5 * t^T * H_w_min * t - (v^T *t)}
        By minimising this using NCG we can approximate s_test (see self.Explain)
        """
        def fmin_inv_hvp(x):
            feed_dict = {
                self.v_placeholder: x        
            }
            hvp = self.sess.run(self.hvp, feed_dict)
            inv_hvp_val = 0.5 * np.dot(np.concatenate(hvp),x) - np.dot(np.concatenate(v),x)
            return inv_hvp_val
        return fmin_inv_hvp
    
    def _get_grad_fmin(self,v):
        """
        Returns the function for calculating the gradient of the fmin function
        at a vector x
        The vector v is treated as a conbstant and varies with each test point
        """
        def _grad_fmin(x):
            feed_dict = {
                self.v_placeholder: x        
            }
            hvp = self.sess.run(self.hvp, feed_dict)
            grad_val = np.concatenate(hvp) - np.concatenate(v)
            return grad_val
        return _grad_fmin
    
    def _get_fmin_hvp(self, v, p):
        """
        Returns the Hessian of the fmin function
        """
        feed_dict = {
                self.v_placeholder: x        
            }
        hvp = self.sess.run(self.hvp, feed_dict)
        return np.concatenate(hvp)
    
    def _get_cg_callback(self, v):
        """
        This function appears to only serve as a display option for the N-CG process
        """
        fmin = self._get_fmin_inv_hvp(v)

        def _fmin_inv_hvp_split(x):        
            feed_dict = {
                self.v_placeholder: x        
            }
            hvp = self.sess.run(self.hvp, feed_dict)
            inv_hvp_val = 0.5 * np.dot(np.concatenate(hvp),x) - np.dot(np.concatenate(v),x)
            return inv_hvp_val
        
        def cg_callback(x):
#            x is current params
            v = self.vec_to_list(x)
            idx_to_rm = 5
            
            single_train_ex = self.train_imgs[idx_to_rm,:].reshape(1,-1)
            single_train_lbl = self.train_lbls[idx_to_rm].reshape(-1)
            feed_dict = {
                    self.input_ : single_train_ex,
                    self.labels_ : single_train_lbl
            }
            grad_train_loss = self.grad_loss(single_train_ex, single_train_lbl)
            predicted_del_loss = np.dot(np.concatenate(v), np.concatenate(grad_train_loss)) / self.train_lbls.shape[0]
            
        return cg_callback
    
    def _get_vec_to_list(self):
        
        def vec_to_list(v):
            return_ls = []
            pos = 0
            for p in self.params:
                return_ls.append(v[pos : pos+len(p)])
                pos += len(p)
            
            assert pos == len(v)
            return return_ls
        
        return vec_to_list