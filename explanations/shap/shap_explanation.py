import numpy as np

from skimage.color import gray2rgb, rgb2gray

from skimage.segmentation import mark_boundaries

import cv2

import shap

import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

import os
import sys
import json

class ShapExplainer(object):
  """docstring for LimeExplainer"""
  def __init__(self, model):
    super(ShapExplainer, self).__init__()
    self.model = model
    self.dataset_tool_dict = {}

  def GetColorMap(self):
    colors = []
    for l in np.linspace(1, 0, 100):
        colors.append((30./255, 136./255, 229./255,l))
    for l in np.linspace(0, 1, 100):
        colors.append((255./255, 13./255, 87./255,l))
    red_transparent_blue = LinearSegmentedColormap.from_list("red_transparent_blue", colors)

    return red_transparent_blue


  def GetBackgroundSamples(self,dataset_name):
    if(dataset_name in self.dataset_tool_dict):
      dataset_tool = self.dataset_tool_dict["dataset_name"]
    else:
      
      def GetProjectExplicitBase(base_dir_name="p5_afm_2018_demo"):
        cwd = os.getcwd()
        split_cwd = cwd.split("/")

        base_path_list = []
        for i in range(1, len(split_cwd)):
          if(split_cwd[-i] == base_dir_name):
            base_path_list = split_cwd[:-i+1]

        if(base_path_list == []):
          raise IOError('base project path could not be constructed. Are you running within: '+base_dir_name)

        base_dir_path = "/".join(base_path_list)

        return base_dir_path

      base_dir = GetProjectExplicitBase(base_dir_name="p5_afm_2018_demo")

      #add dataset folder to sys path to allow for easy import
      datasets_path = os.path.join(base_dir,"datasets")
      sys.path.append(datasets_path)
      ###

      #import dataset tool
      from DatasetClass import DataSet


      #### load dataset json
      data_json_path = os.path.join(datasets_path,"datasets.json")

      datasets_json = None
      with open(data_json_path,"r") as f:
        datasets_json = json.load(f)


      ### get dataset details
      dataset_json = [dataset for dataset in datasets_json["datasets"] if dataset["dataset_name"] == dataset_name][0]


      ### gather required information about the dataset
      if("default_training_allocation_path" in dataset_json.keys()):
        file_path = dataset_json["default_training_allocation_path"]
        load_split = True
      else:
        file_path = dataset_json["ground_truth_csv_path"]
        load_split = False

      image_url_column = "image_path"
      ground_truth_column = "label"
      label_names = [label["label"] for label in dataset_json["labels"]] # gets all labels in dataset. To use a subset of labels, build a list manually
      label_names.sort()
      print(label_names)

      
      ### instantiate dataset tool
      csv_path = os.path.join(datasets_path,"dataset_csvs",file_path)
      print(csv_path)
      dataset_images_dir_path =  os.path.join(datasets_path,"dataset_images")

      dataset_tool = DataSet(csv_path,image_url_column,ground_truth_column,explicit_path_suffix =dataset_images_dir_path) #instantiates a dataset tool

      dataset_tool.CreateLiveDataSet(dataset_max_size = -1, even_examples=True, y_labels_to_use=label_names) #creates an organised list of dataset observations, evenly split between labels


      if(load_split):
        dataset_tool.ProduceDataFromTrainingSplitFile(csv_path,explicit_path_suffix =dataset_images_dir_path)
      else:
        dataset_tool.SplitLiveData(train_ratio=0.8,validation_ratio=0.1,test_ratio=0.1) #splits the live dataset examples in to train, validation and test sets

      self.dataset_tool_dict["dataset_name"] = dataset_tool
    
    source = "train"
    train_x, train_y = dataset_tool.GetBatch(batch_size = 1024,even_examples=True, y_labels_to_use=label_names, split_batch = True,split_one_hot = True, batch_source = source)

    return train_x

  def GenerateShapExplanationImage(self,input_image,shap_values):
    
    
    if(len(input_image.shape) == 4):
      input_image = np.squeeze(input_image)
    
    x_curr = input_image.copy()

    # make sure
    if len(x_curr.shape) == 3 and x_curr.shape[2] == 1:
        x_curr = x_curr.reshape(x_curr.shape[:2])
    if x_curr.max() > 1:
        x_curr /= 255.

    if len(shap_values[0].shape) == 2:
        abs_vals = np.stack([np.abs(shap_values[i]) for i in range(len(shap_values))], 0).flatten()
    else:
        abs_vals = np.stack([np.abs(shap_values[i].sum(-1)) for i in range(len(shap_values))], 0).flatten()
    max_val = np.nanpercentile(abs_vals, 99.9)

    i = 0

    sv = shap_values[i] if len(shap_values[i].shape) == 2 else shap_values[i].sum(-1)
    plt_img = plt.imshow(x_curr, cmap=plt.get_cmap('gray'), alpha=0.15, extent=(0, sv.shape[0], sv.shape[1], 0))
    plt.imshow(sv, cmap=self.GetColorMap(), vmin=-max_val, vmax=max_val)
    plt.axis('off')

    ax = plt.gca()
    canvas = ax.figure.canvas 
    canvas.draw()

    w,h = canvas.get_width_height()
    buf = np.fromstring ( canvas.tostring_rgb(), dtype=np.uint8 )
    buf.shape = ( h, w,3 )

    return buf

  def Explain(self,input_image, additional_args = {}):

    #load additional arguments or set to default
    if("num_background_samples" in additional_args):
      num_background_samples=additional_args["num_background_samples"]
    else:
      num_background_samples=100

    if("background_image_pool" in additional_args):
      background_image_pool=additional_args["background_image_pool"]
    else:
      if("dataset_name" in additional_args):
        background_image_pool=self.GetBackgroundSamples(additional_args["dataset_name"])
      else:
        raise ValueError("Can't perform shap explanation without background images, which can be provided or a dataset name can be provided")
    if("min_weight" in additional_args):
      min_weight=additional_args["min_weight"]
    else:
      min_weight=0.01

    ####SHAP
    # select a set of background examples to take an expectation over
    background = background_image_pool[np.random.choice(background_image_pool.shape[0], num_background_samples, replace=False)]

    e = shap.DeepExplainer(self.model.model, background)
    
    if(len(input_image.shape) == 3 ):
      input_image = np.array([input_image])

    shap_values = e.shap_values(input_image)
    
    
    prediction = self.model.Predict(input_image)
    predicted_class = np.argmax(prediction)
    print("explanation prediction output",prediction)
    print("explanation predicted_class",predicted_class)
    
    explanation = shap_values[predicted_class]

    explanation_image = self.GenerateShapExplanationImage(input_image,explanation)

    ## for testing:
    # shap.image_plot(shap_values, np.multiply(input_image,255.0))

      
    additional_outputs = {"shap_values":[shap_value.tolist() for shap_value in shap_values]}

    explanation_text = "Evidence towards predicted class shown in red, evidence against shown in blue."
    
    return explanation_image, explanation_text, predicted_class, additional_outputs
  


if __name__ == '__main__':
  import os
  import sys
  

  ### Setup Sys path for easy imports
  # base_dir = "/media/harborned/ShutUpN/repos/dais/p5_afm_2018_demo"
  # base_dir = "/media/upsi/fs1/harborned/repos/p5_afm_2018_demo"

  def GetProjectExplicitBase(base_dir_name="p5_afm_2018_demo"):
    cwd = os.getcwd()
    split_cwd = cwd.split("/")

    base_path_list = []
    for i in range(1, len(split_cwd)):
      if(split_cwd[-i] == base_dir_name):
        base_path_list = split_cwd[:-i+1]

    if(base_path_list == []):
      raise IOError('base project path could not be constructed. Are you running within: '+base_dir_name)

    base_dir_path = "/".join(base_path_list)

    return base_dir_path

  base_dir = GetProjectExplicitBase(base_dir_name="p5_afm_2018_demo")


  #add all model folders to sys path to allow for easy import
  models_path = os.path.join(base_dir,"models")

  model_folders = os.listdir(models_path)

  for model_folder in model_folders:
    model_path = os.path.join(models_path,model_folder)
    sys.path.append(model_path)

  print("example not present!")
  # from CNN import SimpleCNN

  # from tensorflow.examples.tutorials.mnist import input_data
  # mnist = input_data.read_data_sets("/tmp/data/", one_hot=False)

  # from skimage.segmentation import mark_boundaries
  # import matplotlib.pyplot as plt

  # model_input_dim_height = 28
  # model_input_dim_width = 28 
  # model_input_channels = 1
  # n_classes = 10 

  # additional_args = {}

  # cnn_model = SimpleCNN(model_input_dim_height, model_input_dim_width, model_input_channels, n_classes, model_dir ="mnist", additional_args = additional_args )

  # test_image = mnist.test.images[:1]
    
  # lime_explainer = LimeExplainer(cnn_model)

  # additional_args = {
  # "num_samples":1000,
  # "num_features":100,
  # "min_weight":0.01
  # }
  # explanation_image, explanation_text, predicted_class, additional_outputs = lime_explainer.Explain(test_image,additional_args)
  
  # # prediction, explanation = lime_explainer.ClassifyWithLIME(test_image,labels=list(range(n_classes)),num_samples=10,top_labels=n_classes)
  # # prediction, explanation = lime_explainer.ClassifyWithLIME(test_image,num_samples=1000,labels=list(range(n_classes)), top_labels=n_classes)

  # predicted_class = np.argmax(prediction)
  # print("predicted_class",predicted_class)
  # print("mnist.test.labels[:1]",mnist.test.labels[:1])

  # print(explanation_text)
  # cv2.imshow("explanation",explanation_image)
  # 