import matplotlib
matplotlib.use('Agg')
import networkx as nx
import csv
import numpy as np
from numpy import ma
from emcee import PTSampler, autocorr
import corner
import time as tm
import copy
import matplotlib.pyplot as plt
import random as rnd
from multiprocess import Pool
import INoDS_convenience_functions as nf
import warnings
from scipy import signal
import scipy.stats as ss
import cPickle
np.seterr(invalid='ignore')
np.seterr(divide='ignore')
warnings.simplefilter("ignore")
warnings.warn("deprecated", DeprecationWarning)
#######################################################################
def log_likelihood(parameters, data, null_comparison, diagnosis_lag,  recovery_prob, nsick_param, **kwargs):
	
	logmin = 100000000
	G_raw, health_data, node_health, nodelist, truth, time_min, time_max, seed_date  =data	
	p = to_params(parameters, null_comparison, diagnosis_lag, nsick_param, recovery_prob)
	health_data_new = copy.deepcopy(health_data)
	node_health_new = copy.deepcopy(node_health)
	if null_comparison:
		network = int(ss.randint.ppf(p['model'][0], 0,  len(G_raw)))
		#assing network
		G = G_raw[network]
	else:
		network=0 
		G= G_raw[0]
	##########################################diagnosis lag
	##impute true infection date and recovery date (if SIR/SIRS...)
	## infection_date = date picked as a day between last healthy report and first sick report
	## and when the degree of node was >0 the previous day
	##recovery_date = date picked as date with uniform probability between first reported sick day and first 
	##healthy date after sick report
	
	infection_date = []
	if diagnosis_lag:
		diag_list = p['diag_lag'][0]
		diag_list = [max(num,0.000001) and min(num,1) for num in diag_list]
		for (node, time1, time2), diag_lag in zip(sorted(contact_daylist[network]), diag_list):
			lag = int(ss.randint.ppf(diag_lag, 0,  len(contact_daylist[network][(node, time1, time2)])))
			new_infection_time  = contact_daylist[network][(node, time1, time2)][lag]
			new_recovery_time = time2
			infection_date.append((node, new_infection_time))
			
		
			if recovery_prob!=np.inf:
				max_recovery_date = recovery_daylist[(node, time1, time2)]
				##uniform ppf is defined as (prob, lower_limite, upper_limit - lower_limit)
				new_recovery_time = int(ss.uniform.ppf(p['gamma'][0], new_infection_time, max_recovery_date-new_infection_date))
				## if the proposed recovery date coincides with a date when the indiv was reported sick then return invalid

				if new_recovery_time<= time2: return -np.inf
			node_health_new[node][1].remove((time1, time2))
			node_health_new[node][1].append((new_infection_time, new_recovery_time))	

			for day in range(new_infection_time, new_recovery_time+1): health_data_new[node][day]=1
			
	else:
		for node in node_health:
			#PS: double check this line for SIS
			if node_health[node].has_key(1): 
				for (time1, time2) in node_health[node][1]:infection_date.append((node,time1))
	#################################################	
	
	infected_degree={key:{} for key in nodelist}
	for node in nodelist: infected_degree[node] = {time: (infected_strength(node, time, health_data_new, G) if node in G[time].nodes() else 0) for time in G.keys()}
	
	#######Rate of learning
	overall_learn = [np.log(calculate_lambda1(p['beta'][0], p['alpha'][0], infected_degree, focal_node, sick_day)) for focal_node, sick_day in sorted(infection_date) if sick_day!=seed_date]
	
	#######Rate of not learning
	overall_not_learn = []
	healthy_nodelist = [(node, healthy_day1, healthy_day2) for node in node_health_new if node_health_new[node].has_key(0) for healthy_day1, healthy_day2 in node_health_new[node][0] ]
	
	for focal_node,healthy_day1, healthy_day2 in sorted(healthy_nodelist):
		lambda_list = [1-calculate_lambda1(p['beta'][0],p['alpha'][0], infected_degree, focal_node, date) for date in range(healthy_day1, healthy_day2+1)]
		overall_not_learn.append(sum([np.log(num) for num in lambda_list]))


	##############################
	loglike = sum(overall_learn) + sum(overall_not_learn)
	#if loglike >-600:print ("likelihood"),  int(ss.randint.ppf(p['model'][0], 0,  len(G_raw))),round(loglike,3), round(ss.expon.logpdf(p['alpha'][0]),3),  round(loglike+ss.expon.logpdf(p['alpha'][0]),3), p['beta'][0], p['alpha'][0]
		
	if loglike == -np.inf or np.isnan(loglike): return -np.inf
	else: return loglike

###############################################################################
def calculate_lambda1(beta1, alpha1, infected_degree, focal_node, date):
	return 1-np.exp(-(beta1*infected_degree[focal_node][date-1] + alpha1))

################################################################################
def infected_strength(node, time1, health_data_new, G):
	
	strength = [G[time1][node][node_i]["weight"] for node_i in G[time1].neighbors(node) if (health_data_new[node_i].has_key(time1) and health_data_new[node_i][time1] == 1)]
	return sum(strength)

################################################################################
def to_params(arr, null_comparison, diagnosis_lag, nsick_param, recovery_prob):
	r""" Converts a numpy array into a array with named fields"""
	
	if recovery_prob==np.inf:
		if diagnosis_lag and null_comparison: 
			return arr.view(np.dtype([('beta', np.float),
				('alpha', np.float),
				('diag_lag', np.float, nsick_param),
				('model', np.float)]))

		elif null_comparison:
			return arr.view(np.dtype([('beta', np.float),
				('alpha', np.float),
				('model', np.float)]))
	
		elif diagnosis_lag: 
			return arr.view(np.dtype([('beta', np.float),
				('alpha', np.float),
				('diag_lag', np.float, nsick_param)]))
			
		return arr.view(np.dtype([('beta', np.float), 
			('alpha', np.float)]))

	if recovery_prob!=np.inf:
		if diagnosis_lag and null_comparison: 
			return arr.view(np.dtype([('beta', np.float),
				('alpha', np.float),
				('gamma', np.float),
				('diag_lag', np.float, nsick_param),
				('model', np.float)]))

		elif null_comparison:
			return arr.view(np.dtype([('beta', np.float),
				('alpha', np.float),
				('gamma', np.float),
				('model', np.float)]))
	
		elif diagnosis_lag: 
			return arr.view(np.dtype([('beta', np.float),
				('alpha', np.float),
				('gamma', np.float),
				('diag_lag', np.float, nsick_param)]))
			
		return arr.view(np.dtype([('beta', np.float), 
			('alpha', np.float),
			('gamma', np.float)]))
	

#####################################################################
def autocor_checks(sampler, burnin, itemp=0, outfile=None):
    
	print('Chains contain samples ='), sampler.chain.shape[-2]
    	print('Specified burn-in is samples'), burnin
	a_exp = sampler.acor[0]
	a_int = np.max([autocorr.integrated_time(sampler.chain[itemp, i, burnin:]) for i in range(sampler.chain.shape[1])], 0)
	a_exp = max(a_exp)
	a_int = max(a_int)
	print('A reasonable burn-in should be around steps'), int(10 * a_exp)
	print('After burn-in, each chain produces one independent sample per steps ='), int(a_int)
	return a_exp, a_int

#####################################################################
def log_evidence(sampler, burnin, outfile=None):

	#(10, 196, 1)

	logls = sampler.lnlikelihood[:, :, burnin:]
	logls = ma.masked_array(logls, mask=logls == -np.inf)
	
	mean_logls = logls.mean(axis=-1).mean(axis=-1)
	logZ = -np.trapz(mean_logls, sampler.betas)
	logZ2 = -np.trapz(mean_logls[::2], sampler.betas[::2])
	logZerr = abs(logZ2 - logZ)
	return logZ, logZerr

#####################################################################

def flatten_with_burn(sampler, burnin):
    c = sampler.chain
    c = c[0,:, burnin:]
    ct = c.reshape((np.product(c.shape[:-1]), c.shape[-1]))
    return c.reshape((np.product(c.shape[:-1]), c.shape[-1]))

#######################################################################
def summary(samples):

    #print signal.find_peaks_cwt(samples[:,0], np.arange(0,0.5))
    mean = samples.mean(0)
    mean = [round(num,3) for num in mean]
    sigma = samples.std(0)
    sigma = [round(num,3) for num in sigma]
    return mean, sigma

##############################################################################
def log_prior(parameters, priors, null_comparison, diagnosis_lag, nsick_param, recovery_prob):
    
    p = to_params(parameters, null_comparison, diagnosis_lag, nsick_param, recovery_prob)
    if p['beta'][0] <  priors[0][0] or p['beta'][0] > priors[0][1]: return -np.inf
    if p['alpha'][0] < priors[1][0]  or  p['alpha'][0] >  priors[1][1]: return -np.inf 
    if recovery_prob != np.inf:
	if p['gamma'][0] < recovery_prob[0]  or  p['gamma'][0] >  recovery_prob[1]: return -np.inf 
 
    if diagnosis_lag: 
	if (p['diag_lag'][0] < 0.000001).any() or (p['diag_lag'][0] > 1).any():return -np.inf

    if null_comparison:
	if p['model'][0] < 0.000001  or  p['model'][0] >  1: return -np.inf 
   
    	
    return  ss.powerlaw.logpdf((1-p['alpha'][0]), 4)
#######################################################################
def start_nbda(data,  recovery_prob,  priors,  niter, nburn, verbose, diagnosis_lag=False, null_comparison=False, **kwargs):
	
	G_raw, health_data, node_health, nodelist, true_value,  time_min, time_max, seed_date =data	
	
	if diagnosis_lag:
		contact_daylist = nf.return_contact_days_sick_nodes(node_health, seed_date, G_raw)
		truth_of_lag = nf.compute_diagnosis_lag_truth(G_raw[0], contact_daylist[0], "True_health_data.csv")
		nsick_param = len(contact_daylist[0])
		recovery_daylist = nf.return_potention_recovery_date(node_health, time_max, G_raw)
	else: nsick_param = 0
	
	######################################
	### Set number of parameters to estimate
	######################################
	ndim_base = 2
	if recovery_prob != np.inf: ndim_base +=1
	ndim = ndim_base+nsick_param
	if null_comparison: ndim += 1 

	if verbose: print ("Number of dimension"), ndim
	
	nwalkers = max(20, 2*ndim) # number of MCMC walkers

	####################### 
	##Adjust temperature ladder
	#######################
	if null_comparison:
		betas = np.concatenate((np.linspace(0, -0.1, 20),
                                    np.linspace(-0.12, -0.5, 5),
                                    np.linspace(-0.5, -1, 5)))
		betas = 10**(np.sort(betas)[::-1])
		ntemps = 30
		
	else:
		betas = np.linspace(0, -0.04, 10)
		betas = 10**(np.sort(betas)[::-1])
		ntemps = 10

	####################### 
	###print true likelihood
	#######################
	if verbose:print ("true likelihood value"), log_likelihood(np.array(true_value), data, null_comparison, diagnosis_lag,recovery_prob, nsick_param)
	
		
	####################### 
	###set starting positions
	#######################
	starting_guess = np.zeros((ntemps, nwalkers, ndim))
	##starting guess for beta  
	starting_guess[:, :, 0] = np.random.uniform(low = priors[0][0], high = priors[0][1], size=(ntemps, nwalkers))
	##start alpha close to zero
	alphas = np.random.power(4, size = (ntemps, nwalkers))
	starting_guess[:, :, 1] = 1-alphas
	if recovery_prob != np.inf:
		starting_guess[:, :, 2] = np.random.uniform(low = recovery_prob[0], high = recovery_prob[1], size=(ntemps, nwalkers))
	if diagnosis_lag:
		starting_guess[:, :, ndim_base: ndim_base+nsick_param] = np.random.uniform(low = 0.001, high = 1,size=(ntemps, nwalkers, nsick_param))
		
	if null_comparison:
		starting_guess[:, :, -1] = np.random.uniform(low = 0.0001, high =1, size=(ntemps, nwalkers))
	 

	####################################
	if verbose: print ("burn in......")
	if diagnosis_lag: 
		sampler = PTSampler(ntemps=ntemps, nwalkers=nwalkers, dim=ndim, betas=betas, logl=log_likelihood, logp=log_prior, a = 1.5,  loglargs=(data, null_comparison, diagnosis_lag, recovery_prob,  nsick_param, contact_daylist), logpargs=(priors, null_comparison, diagnosis_lag, nsick_param , recovery_prob), threads=4) 
	else: 
		sampler = PTSampler(ntemps=ntemps, nwalkers=nwalkers, dim=ndim, betas=betas, logl=log_likelihood, logp=log_prior, a = 1.5,  loglargs=(data, null_comparison, diagnosis_lag,  recovery_prob, nsick_param), logpargs=(priors, null_comparison, diagnosis_lag, nsick_param, recovery_prob), threads=4) 
	
	for i, (p, lnprob, lnlike) in enumerate(sampler.sample(starting_guess, iterations=10)):
		print("burnin progress"), (100 * float(i) /50)
		
		

	sampler.reset()	
	
	#################################
	print ("sampling........")
	nthin = 1
	for i, (p, lnprob, lnlike) in enumerate(sampler.sample(p, lnprob0 = lnprob,  lnlike0= lnlike, iterations= niter, thin= nthin)):  
		print("sampling progress"), (100 * float(i) / niter)
		
		
	##############################

	#The resulting samples are stored as the sampler.chain property:
	assert sampler.chain.shape == (ntemps, nwalkers, niter/nthin, ndim)
	
	return sampler
##############################################3
def getstate(sampler):
        self_dict = sampler.__dict__.copy()
        del self_dict['pool']
	return self_dict

##############################################################################################
def summarize_sampler(sampler, G_raw, nburn, true_value, output_filename, summary_type):


	# Longest autocorrelation length (over any temperature)
	#max_acl = np.max(sampler.acor)	
	#if verbose: print ("Longest autocorrelation length (over any temperature)"), max_acl
	print ("Mean burnin acceptance fraction is"),  np.mean(sampler.acceptance_fraction)

	##save chain
	if summary_type =="parameter_estimate":
		cPickle.dump(getstate(sampler), open( output_filename + "_" + summary_type +  ".p", "wb" ), protocol=2)
		fig = corner.corner(sampler.flatchain[0, :, 0:2], quantiles=[0.16, 0.5, 0.84], labels=["$beta$", "$alpha$"], truths= true_value, truth_color ="red")
		fig.savefig(output_filename + "_" + summary_type +"_posterior.png")
		nf.plot_beta_results(sampler, nburn, filename = output_filename + "_" + summary_type +"_beta_walkers.png" )
		logz, logzerr = log_evidence(sampler, nburn)
		print ("Model evidence and error"), logz, logzerr
			
	stats={}
	samples = flatten_with_burn(sampler, nburn)
	stats['mean'], stats['sigma'] = summary(samples)
	try:stats['a_exp'], stats['a_int'] = autocor_checks(sampler, nburn)
	except: print ("Warning!! Autocorrelation checks could not be performed. Sampler chains may be too short")        
	##plot results
	
	#################################
	if summary_type =="null_comparison":
		cPickle.dump(getstate(sampler), open( output_filename + "_" + summary_type +  ".p", "wb" ), protocol=2)
		#fig = corner.corner(sampler.flatchain[0, :, -1], quantiles=[0.16, 0.5, 0.84], labels=["Network"],  truths= true_value[-1], truth_color ="red")
		#fig.savefig(
		N_networks = len(G_raw)
		sampler1 = sampler.flatchain[0, :, 2]
		bins = [0]+[ss.randint.cdf(num, 0, N_networks) for num in xrange(N_networks)]
		hist = np.histogram(sampler1, bins)[0]
		print ("# times models visited"), [num for num in xrange(N_networks)], hist
		ind = [num for num in xrange(N_networks)]
		plt.clf()		
		plt.hist(hist[1:])
		plt.axvline(x=hist[0], ymin=0, ymax=max(hist), color='red', label ="Network hypothesis")
		plt.xlabel("Predictive power")
		plt.ylabel("Frequency")
		plt.legend()
		plt.savefig(output_filename + "_" + summary_type +"_posterior.png")
	
	

#######################################################################
def find_aggregate_timestep(health_data):
	"""Returns the timestep where all infection status are reported """

	timelist = []
	for node in health_data.keys():
		for time in health_data[node].keys(): timelist.append(time)

	if len(list(set(timelist)))!=1: print("Place error message here")
	return list(set(timelist))[0]
	
######################################################################33
def run_nbda_analysis(edge_filename, health_filename, output_filename, nodelist, recovery_prob, truth, null_networks, priors,  iteration, burnin, verbose=True, null_comparison=False, normalize_edge_weight=False, diagnosis_lag=True,**kwargs):
	"""Main function for NBDA """

	####################
	health_data, node_health = nf.extract_health_data(health_filename, nodelist)
	seed_date = nf.find_seed_date(node_health)
	time_min = 0
	time_max = max([key for node in health_data.keys() for key in health_data[node].keys()])
	G_raw = {}
	G_raw[0] = nf.create_dynamic_network(edge_filename, normalize_edge_weight)
	
	###################
	##Step 1: Estimate unknown parameters of HA.
	true_value = truth[:-1]
	data1 = [G_raw, health_data, node_health, nodelist, true_value,  time_min, time_max, seed_date]
	print ("estimating model parameters.........................")
	sampler  = start_nbda(data1,  recovery_prob, priors,  iteration, burnin, verbose, diagnosis_lag=False, null_comparison=False)
	summarize_sampler(sampler, G_raw, burnin, true_value, output_filename, summary_type = "parameter_estimate")
	####################
	
	if null_comparison:
		for num in xrange(null_networks):G_raw[num+1] = nf.randomize_network(G_raw[0])
	
	true_value = truth
	data1 = [G_raw, health_data, node_health, nodelist, true_value, time_min, time_max, seed_date]
	print ("comparing network hypothesis with null............................")
	sampler = start_nbda(data1, recovery_prob, priors,  iteration, burnin, verbose, diagnosis_lag=False, null_comparison=True, null_networks=null_networks)
	summarize_sampler(sampler, G_raw, burnin, true_value, output_filename, summary_type = "null_comparison")
	
	
	#for trial in xrange(5):
	#	print ("running permuted network")
	#	G1_raw = {}
	#	G1_raw[0] =  nf.permute_network(G_raw[0], 0.4)
	#	data1 = [G1_raw, health_data, node_health, nodelist, null_comparison, diagnosis_lag, time_min, time_max, seed_date]
	#	lnZ_mod1, err_mod1 = start_nbda(data1, priors,  iteration, burnin, verbose, null_networks=null_networks)
	#	print('estimated evidence & error NULL MODEL = '),trial, lnZ_mod1, err_mod1
	
######################################################################33
if __name__ == "__main__":

	print ("run the run_inods.py file")

	