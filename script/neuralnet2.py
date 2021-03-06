#!/usr/bin/env python

import rospy
from move_base_msgs.msg import MoveBaseAction, MoveBaseGoal
import actionlib
from actionlib_msgs.msg import *
from geometry_msgs.msg import Pose, PoseWithCovarianceStamped, Point, Quaternion, Twist

import math, random, time, datetime
import cv2, os, glob, sys
import dataset
import numpy as np
import tensorflow as tf 
from datetime import timedelta
from threading import Timer

print("This file directory only")
print(os.getcwd())

cap = cv2.VideoCapture(1)
#cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280) #1280  640
#cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720) #720   480
cap.set(cv2.CAP_PROP_FPS, 0.01)
# filewrite_img = False
img_width = 640
img_height = 480
imshow = True
display = True
# alpha = 0.1
threshold = 19.68	#21  17    0.15   21   1.7            20.5   18.5  for test
threshold1 = 20.02      #22.1   20   0.4   23.5   1.95         22.3    24.3 for test 20.65
iou_threshold = 8.9#.5
# filewrite_img = False

# classes info
classes = ["left", "right"]
num_classes = len(classes)
num_classes1 = 588 #1470 #match the dimension size 588

train_path = '/home/l/catkin_ws/src/robot_detection/script/train_image'
test_path = 'test_image'

# validation split / 20% of validation
validation_size = .3

# batch 16
batch_size = 16

# img_dimensions(only squares) 
img_size = 448 #128

# color channels for images: 1 channel for gray scale
num_channels = 3

# image size when flattened to the single dimension
img_size_flat = img_size * img_size * num_channels

x = tf.placeholder(tf.float32, shape = [None, img_size,img_size,num_channels], name = 'x')

# read the training data 
data = dataset.read_train_sets(train_path, img_size, classes, validation_size = validation_size)

def weights(shape):
	return tf.Variable(tf.truncated_normal(shape, stddev=0.1)) # 0.05 0.005

def biases(length):
	return tf.Variable(tf.constant(0.1, shape = [length])) # 0.05  0.005

# layer configuration
# preivous layer, number of channels in previous layer, width and height of each filter, number of filter, 2x2 max pooling
def convolution_layer(inputs, filter_size, num_filters, stride):
	channels = inputs.get_shape()[3]
	# shape of the filter-weights for the convolution. This format is determined by the Tensorflow API
	shape = [filter_size, filter_size, int(channels), num_filters]
		# create new weights. Filters with the given shape
	w = weights(shape = shape)
	# create new biases, one for each filter
	b = biases(length = num_filters)

	pad_size = filter_size//2
	pad_mat = np.array([[0,0],[pad_size, pad_size],[pad_size, pad_size],[0,0]])
	inputs_pad = tf.pad(inputs, pad_mat)

	# create the tensorflow operation for convolution. The strides are set to 1 in all dimension. the first and last stride must always be 1, because the first is for the number of image and the
	# last is for the input-channel, but for example the strides = 1, 2, 2, 1 would mean that the filter is moved 2 pixels across the x and y-axis of the image. the padding is set to 'same' wich means the input image
	layer = tf.nn.conv2d(inputs_pad, w, strides=[1, stride, stride, 1], padding='SAME')

	#  is padded with zeroes therefore, the ouput size is the same
	# layer = tf.nn.conv2d(inputs, w, strides = [1, stride, stride, 1], padding = 'SAME') # 1 2 2 1
	layer = tf.add(layer,b)

	return layer, w

def pooling_layer(inputs,size,stride):
		# print 'Create ' + str(inputs) + ' : pool'
		return tf.nn.max_pool(inputs, ksize=[1, size, size, 1],strides=[1, stride, stride, 1], padding='SAME')#,name=str(inputs)+'_pool')

def flatten_layer(layer):
	# get the shape of the input layer
	layer_shape = layer.get_shape()

	# the shape of the input layer is assumed to be:layer_shape == [num_images, img_height, img_width, num_channels] the number of features: img_height * img_width * numchannels
	# we can use a function from tensorflow to calculate this.
	num_features = layer_shape[1:4].num_elements()

	# reshape the layer to [num_images, num_filterseatures]. We just set the size of second dimension to num_features and the size of the first dimension to -1 which means the size in that dimension is calculated
	# so the total size of tensor is unchanged from the reshaping
	flat_layer = tf.reshape(layer, [-1, num_features])

	# the shape of the flattened layer: [num_images, img_height * img_width * num_channels] return both the flattened layer and the number of features.
	return flat_layer, num_features

#  the previous layer, number of input from previous layerm, number of output, use rectified linear unit(relu)
def fully_connected_layer(inputs, hiddens, use_relu = True):
	input_shape = inputs.get_shape().as_list()
	dim = input_shape[1]
	# create new weights and biases
	w = weights(shape = [dim, hiddens])
	b = biases(length = hiddens)

	# calculate the layer as the matrix multiplication of the input and weights, then add the bias-values.
	layer = tf.matmul(inputs, w) + b

	# use relu
	if use_relu:
		layer = tf.nn.relu(layer)

	return layer

# network configuration
convnet1, weights_conv1 = \
convolution_layer(inputs = x, filter_size = 3, num_filters = 16, stride = 1)
# convolution_layer(input = x_image, num_input_channels = num_channels, filter_size = filter_size1, num_filters = num_filters1, use_pooling = True)
#print("now layer2 input")
#print(convnet1.get_shape())		    
pool_layer1 = pooling_layer(convnet1, 2, 2)

convnet2, weights_conv2 = \
convolution_layer(inputs = pool_layer1, filter_size = 3, num_filters = 32, stride = 1)

pool_layer2 = pooling_layer(convnet2, 2, 2)

convnet3, weights_conv3 = \
convolution_layer(inputs = pool_layer2, filter_size = 3, num_filters = 64, stride = 1)
#print("now layer flatten input")
#print(convnet3.get_shape())
pool_layer3 = pooling_layer(convnet3, 2, 2)

convnet4, weights_conv4 = \
convolution_layer(inputs = pool_layer3, filter_size = 3, num_filters = 128, stride = 1)

pool_layer4 = pooling_layer(convnet4, 2, 2)

convnet5, weights_conv5 = \
convolution_layer(inputs = pool_layer4, filter_size = 3, num_filters = 256, stride = 1)

pool_layer5 = pooling_layer(convnet5, 2, 2)

convnet6, weights_conv6 = \
convolution_layer(inputs = pool_layer5, filter_size = 3, num_filters = 512, stride = 1)

pool_layer6 = pooling_layer(convnet6, 2, 2)

convnet7, weights_conv7 = \
convolution_layer(inputs = pool_layer6, filter_size = 3, num_filters = 512, stride = 1)

flat_layer, num_features = flatten_layer(convnet7)

fully_connected1 = \
fully_connected_layer(inputs = flat_layer, hiddens = 256, use_relu= False)

fully_connected2 = \
fully_connected_layer(inputs = fully_connected1, hiddens = 4096, use_relu= True)

fc3 = \
fully_connected_layer(inputs = fully_connected2, hiddens = 1470, use_relu= True)

# y_true = tf.placeholder(tf.float32, shape = [None, num_classes], name = 'y_true')
y_true = tf.placeholder(tf.float32, shape = [None, 1470], name = 'y_true')
y_true_class = tf.argmax(y_true, dimension = 1)
# prediction
y_pred = tf.nn.softmax(fc3, name = 'y_pred')
y_pred_class = tf.argmax(y_pred, dimension = 1)
# session.run(tf.initialize_all_variables())
# session.run(tf.global_variables_initializer())
cross_entropy = tf.nn.softmax_cross_entropy_with_logits(logits = fc3, labels = y_true) 
#labels: Each row labels[i] must be a valid probability distribution. logits: Unscaled log probabilities.
cost = tf.reduce_mean(cross_entropy)
# optimization
# learning_rate = tf.train.exponential_decay()
# optimizer = tf.train.GradientDescentOptimizer(learning_rate=1e-5).minimize(cost) #1e-4   AdamOptimizer
optimizer = tf.train.AdamOptimizer(learning_rate=1e-7).minimize(cost) # 1e-5
correct_prediction = tf.equal(y_pred_class, y_true_class)
accuracy = tf.reduce_mean(tf.cast(correct_prediction, tf.float32))

session = tf.Session()
session.run(tf.global_variables_initializer())

def print_progress(period, feed_dict_train, feed_dict_validate, loss, clock):
	# calculate the accuracy on the training-set
	acc= session.run(accuracy, feed_dict = feed_dict_train)
	val_acc = session.run(accuracy, feed_dict = feed_dict_validate) #feed_dict_validate
	clock = time.time()
	strtime = str(time.time()-clock)
	msg = "training number {0} --- Training : {1: > 6.1%},  Accuracy: {2: > 6.1%}, loss: {3:}, Time: {4:}"
	print(msg.format(period + 1, acc, val_acc, loss, clock)) # period + 1: JUST ADD ONE, ..., strtime

total_iterations = 0
train_batch_size = batch_size
saver = tf.train.Saver()
gpu_options = tf.GPUOptions(per_process_gpu_memory_fraction=0.95)

# def training(num_iterations):
	
	
# 	global total_iterations

# 	for i in range(total_iterations, total_iterations + num_iterations): # num_iterations
	
# 		# get a batch of training examples. x_batch holds a batch of images and y_true_batch are the true labels for those images
# 		x_batch, y_true_batch, _, cls_batch = data.train.next_batch(train_batch_size) # image, label, ids, class
# 		x_valid_batch, y_valid_batch, _, valid_cls_batch = data.valid.next_batch(train_batch_size) # image, label, ids, class

# 		# put batch into a dict with the proper names for placeholder variables in the tensorflow graph
# 		feed_dict_train = {x: x_batch, y_true: y_true_batch} # image, label
# 		feed_dict_validate = {x: x_valid_batch, y_true: y_valid_batch} # image, label

# 		session.run(optimizer, feed_dict=feed_dict_train)
# 		# print status at end of each period(defined as full pass through training dataset)
# 		if i % int(data.train.num_examples / batch_size) == 0:	
# 			loss = session.run(cost, feed_dict = feed_dict_validate) ###########fc_19, cost, feed_dict_validate  val_loss
# 			# train_loss = session.run(cost, feed_dict = feed_dict_train)
# 			period = int(i / int(data.train.num_examples / batch_size))
# 			clock = time.time()
# 			print_progress(period, feed_dict_train, feed_dict_validate, loss, clock)
# 			saver.save(session, "model_v6_test.ckpt")
# 			# print(y_true_batch)	
		
# 	# update the total iteration number performed
# 	total_iterations += num_iterations
	
# training(num_iterations = 10)

saver.restore(session, "/home/l/catkin_ws/src/robot_detection/script/weight/model1040.ckpt")

def detection(img):
	sec = time.time()
	img_height, img_width,_ = image.shape
	re_img = cv2.resize(image, (480, 480)) #448 or 128
	RGB_img = cv2.cvtColor(re_img,cv2.COLOR_BGR2RGB)
	re_img_np = np.asarray(RGB_img)
	inputs = np.zeros((1, 480, 480, 3), dtype='float32') #448
	inputs[0] = (re_img_np/255.0)*2.0-1.0
	input_dict = {x: inputs}
	# print(inputs[0])
	network_output = session.run(fc3, feed_dict=input_dict)
	#print(network_output[0])
	out_box = interpretation(network_output[0])
	dispaly_output(image, out_box)
	strtime = str(time.time()-sec)
	if view : print ('Elapsed time : ' + strtime + ' secs' + '\n')

def interpretation(output):
	pred_prob = np.zeros((7,7,2,2))
	class_probs = np.reshape(output[0:98],(7,7,2))
	scales = np.reshape(output[98:196],(7,7,2))
	out_boxes = np.reshape(output[196:],(7,7,2,4))
	offset = np.transpose(np.reshape(np.array([np.arange(7)]*14),(2,7,7)),(1,2,0))

	out_boxes[:,:,:,0] += offset
	out_boxes[:,:,:,1] += np.transpose(offset,(1,0,2))
	out_boxes[:,:,:,0:2] = out_boxes[:,:,:,0:2] / 7.0
	out_boxes[:,:,:,2] = np.multiply(out_boxes[:,:,:,2],out_boxes[:,:,:,2])
	out_boxes[:,:,:,3] = np.multiply(out_boxes[:,:,:,3],out_boxes[:,:,:,3])
	
	out_boxes[:,:,:,0] *= img_width
	out_boxes[:,:,:,1] *= img_height
	out_boxes[:,:,:,2] *= img_width
	out_boxes[:,:,:,3] *= img_height

	for i in range(2):
		for j in range(2):
			pred_prob[:,:,i,j] = np.multiply(class_probs[:,:,j],scales[:,:,i])

	# if pred_prob>=threshold and probs<=threshold1 :
	filter_mat_probs = (np.array(threshold1>=pred_prob,dtype='bool') & np.array(pred_prob>=threshold,dtype='bool'))
	# filter_mat_probs = np.array(pred_prob>=threshold,dtype='bool')
	filter_mat_boxes = np.nonzero(filter_mat_probs)
	boxes_filtered = out_boxes[filter_mat_boxes[0],filter_mat_boxes[1],filter_mat_boxes[2]]
	probs_filtered = pred_prob[filter_mat_probs]
	classes_num_filtered = np.argmax(filter_mat_probs,axis=3)[filter_mat_boxes[0],filter_mat_boxes[1],filter_mat_boxes[2]] 

	argsort = np.array(np.argsort(probs_filtered))[::-1]
	boxes_filtered = boxes_filtered[argsort]
	probs_filtered = probs_filtered[argsort]
	classes_num_filtered = classes_num_filtered[argsort]
	
	for i in range(len(boxes_filtered)):
		if probs_filtered[i] == 0 : continue
		for j in range(i+1,len(boxes_filtered)):
			if iou(boxes_filtered[i],boxes_filtered[j]) > iou_threshold : 
				probs_filtered[j] = 0.0
	
	filter_iou = np.array(probs_filtered>0.0,dtype='bool')
	boxes_filtered = boxes_filtered[filter_iou]
	probs_filtered = probs_filtered[filter_iou]
	classes_num_filtered = classes_num_filtered[filter_iou]

	result = []
	for i in range(len(boxes_filtered)):
		result.append([classes[classes_num_filtered[i]],boxes_filtered[i][0],boxes_filtered[i][1],boxes_filtered[i][2],boxes_filtered[i][3],probs_filtered[i]])

	return result
count = 0
count1 = 0
def dispaly_output(img,results):
	view = img.copy()

        rospy.init_node('nav_test', anonymous=False)
	move_base = actionlib.SimpleActionClient("move_base", MoveBaseAction)
	
	for i in range(len(results)):
		x = int(results[i][1]) 
		y = int(results[i][2]) 
		w = int(results[i][3]) * 3   #3  1  +100  
		h1 = int(results[i][4]) // 2   #    //4
                
		#x1 = int(results[0][1])
		#y1 = int(results[0][2])
		#w1 = int(results[0][3])//3
		#h1 = int(results[0][4])+800
                #results[0][5] = results[0][5] * .8
		# x = abs(x)
		# y = abs(y)
		w = w + 30
		h = int(h1) * 6 
		#w = w * 4 #with +100
		#w = w // 2# with +100  
		#count = i+1
		results[i][5] = results[i][5] * 3.1 +(h1*0.15)
		locations = dict()
		locations['lab1'] = Pose(Point(51.967, 45.673, 0.000), Quaternion(0.000, 0.000, -0.670, 0.743))
		locations1 = dict()
		locations1['lab1'] = Pose(Point(52.041, 42.851, 0.000), Quaternion(0.000, 0.000, -0.670, 0.743))		
			
		if results[i][0] == 'right':	
		#	for count in range(1,100):
			count1 = 0
			global count 
			count = count + 1
			print count
							
			if count > 50:    
				print(results[i][0] + 'start')
				goal = MoveBaseGoal()
				goal.target_pose.header.frame_id = 'map' # base_link
				goal.target_pose.header.stamp = rospy.Time.now()

				goal.target_pose.pose = locations['lab1']				
#				goal.target_pose.pose.position.x = 0.5 #3.0 3 meters
#				goal.target_pose.pose.orientation.w = 1.0 #1.0 go forward

				#start moving 
				move_base.send_goal(goal)
		elif results[i][0] == 'left':
			global count1
			count = 0
			count1 += 1
			print count1
			if count1 > 50:    
				print(results[i][0] + 'start')
				goal = MoveBaseGoal()
				goal.target_pose.header.frame_id = 'map' # base_link
				goal.target_pose.header.stamp = rospy.Time.now()

				goal.target_pose.pose = locations1['lab1']
				#start moving 
				move_base.send_goal(goal)

		if display : 
				print ('    class : ' + results[i][0] + ' , [x,y,w,h]=[' + str(x) + ',' + str(y) + ',' + str(int(results[i][3])) + ',' + str(int(results[i][4]))+'], Confidence = ' + str(results[i][5]))
				
				if results[i][0] == 'left' and int(threshold) <= 19.4:
					count = 0
					#x = x + 1
					#y = y + 1
					h = int(h)//10 #380
					#h = h*2
					w = int(w)*5  #240
					#w = w*2
					print ('    class : ' + results[0][0] + ' , [x,y,w,h]=[' + str(x) + ',' + str(y) + ',' + str(int(results[0][3])) + ',' + str(int(results[0][4]))+'], Confidence = ' + str(results[0][5]))
				
		if imshow:
			cv2.rectangle(view,(x-w,y-h),(x+w,y+h),(0,255,0),5) # 0 255 0 2
			cv2.putText(view,'Detecting: ' + results[i][0] + ' - %.2f' % results[i][5]+'%',(x-w+5,y-h+350),cv2.FONT_HERSHEY_SIMPLEX,0.8,(0,0,255),2) # +5 -7 #0.5 000 1  # 
			if 	results[i][0] == 'left':		
				cv2.rectangle(view,(x-w,y-h),(x+w,y+h),(0,255,255),5) # 0 255 0 2
			# cv2.rectangle(view,(x-w,y-h-20),(x+w,y-h),(125,125,125),-5) # 125 125 125 -1
			
				cv2.putText(view,'Detecting: ' + results[0][0] + ' - %.2f' % results[0][5]+'%',(x-w+5,y-h+100),cv2.FONT_HERSHEY_SIMPLEX,0.8,(0,255,255),2) # +5 -7 #0.5 000 1  # 
		# if self.filewrite_txt :				
		# 	ftxt.write(results[i][0] + ',' + str(x) + ',' + str(y) + ',' + str(w) + ',' + str(h)+',' + str(results[i][5]) + '\n')
	# if self.filewrite_img : 
	# 	if self.display : print ('    image file writed : ' + self.tofile_img)
	# 	cv2.imwrite(self.tofile_img,view)			
	if imshow :
		#cv2.namedWindow("detection", cv2.WND_PROP_FULLSCREEN)
		#cv2.setWindowProperty("detection",cv2.WND_PROP_FULLSCREEN,cv2.WINDOW_FULLSCREEN)
		cv2.namedWindow("detection", cv2.WINDOW_NORMAL) #WINDOW_AUTOSIZE
		#cv2.setWindowProperty("detection",cv2.WND_PROP_AUTOSIZE,cv2.WINDOW_AUTOSIZE)		
		cv2.imshow('detection',view)
		cv2.waitKey(1)
	# if self.filewrite_txt : 
	# 	if self.display : print ('    txt file writed : ' + self.tofile_txt)
	# 	ftxt.close()
		return results		 

def iou(box_i,box_j):
	
	true_box = \
	min(box_i[0]+0.5*box_i[2],box_j[0]+0.5*box_j[2])-max(box_i[0]-0.5*box_i[2],box_j[0]-0.5*box_j[2])
	pred_box = \
	min(box_i[1]+0.5*box_i[3],box_j[1]+0.5*box_j[3])-max(box_i[1]-0.5*box_i[3],box_j[1]-0.5*box_j[3])
	
	if true_box < 0 or pred_box < 0 : intersection = 0
	else : intersection =  true_box * pred_box
	return intersection / (box_i[2] * box_i[3] + box_j[2] * box_j[3] - intersection)

	# def training(self): #TODO add training function!
	# 	return None


#rospy.init_node('nav_test', anonymous=False)
#results = []
#while(True):
#	ret, frame = cap.read()
#	detect_from_cvmat(frame)
#	move_base = actionlib.SimpleActionClient("move_base", MoveBaseAction)
#	for i in range(len(results)):
#			if dispaly_output(results[i][0]) == 'right':
				#we'll send a goal to the robot to move 3 meters forward
#				goal = MoveBaseGoal()
#				goal.target_pose.header.frame_id = 'base_link'
#				goal.target_pose.header.stamp = rospy.Time.now()
#				goal.target_pose.pose.position.x = 3.0 #3 meters
#				goal.target_pose.pose.orientation.w = 1.0 #go forward

#				#start moving 
#				self.move_base.send_goal(goal)

#				#allow TurtleBot up to 60 seconds to complete task
#				success = self.move_base.wait_for_result(rospy.Duration(60)) 


#				if not success:
#							self.move_base.cancel_goal()
#							rospy.loginfo("The base failed to move forward 3 meters for some reason")
#				else:
#					# We made it!
#					state = self.move_base.get_state()
#					if state == GoalStatus.SUCCEEDED:
#						rospy.loginfo("Hooray, the base moved 3 meters forward")
#	
#	if cv2.waitKey(1) & 0xFF == ord('q'):
#			  break



#cap.release()
#cv2.destroyAllWindows()
