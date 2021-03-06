
from lib.config import cfg
import torch
import numpy as np
from model.encoder import *
import torch.nn as nn
from collections import defaultdict
from lib.utilis.average_meter import AverageMeter
import logging
import csv
import os
import torch.nn.functional as F

from lib.ssim import SSIM 
import random
from lib.utilis.net import save_ckpt
import torchvision
def Trainer(loader, model):
    losses_record = defaultdict(AverageMeter)

    optimizer = torch.optim.Adam(model.parameters())
    
    L1_loss_img = nn.L1Loss().to(cfg.TRAIN.DEVICE)
    L2_loss_img = nn.MSELoss().to(cfg.TRAIN.DEVICE)
    L1_loss_wm = nn.L1Loss().to(cfg.TRAIN.DEVICE)
    L2_loss_wm = nn.MSELoss().to(cfg.TRAIN.DEVICE)

    # loss = loss.to(cfg.TRAIN.DEVICE)
    ssim_losser = SSIM(data_range=1., channel=3).cuda()

    train_img_DataLoder, val_img_DataLoder = loader
    cfg.TRAIN.STEP_PER_EPOCH = int(len(train_img_DataLoder.dataset)/cfg.TRAIN.BATCH_SIZE)
    cfg.VAL.STEP_PER_EPOCH   = int(len(val_img_DataLoder.dataset)/cfg.TRAIN.BATCH_SIZE)

    for epoch in range(cfg.TRAIN.START_EPOCH , cfg.TRAIN.EPOCHS + 1):
        model.train()

        logging.info('TRAIN EPOCH: {}'.format(epoch))

        # TRAIN
        for step, (img, _) in enumerate(train_img_DataLoder):

            cfg.Noiser.RANDOM_NUM = random.randint(0,3)
            # print(cfg.Noiser.RANDOM_NUM)  
            img = img.to(cfg.TRAIN.DEVICE)

            wm = np.random.choice([0, 1], (cfg.TRAIN.BATCH_SIZE, 1, cfg.DATA_SET.H_WM, cfg.DATA_SET.W_WM ))
            wm = torch.Tensor(wm)
            # wm = wm - 0.5
            wm = wm.to(cfg.TRAIN.DEVICE)
            # print(torch.max(img))
            # print(torch.min(img))
        
            with torch.enable_grad():

                # backward
                img_wm, img_noise, wm_decoded = model(img, wm)
                optimizer.zero_grad()

                l1_img = L1_loss_img(img_wm, img)
                l2_img = L2_loss_img(img_wm, img)

                l1_wm = L1_loss_wm(wm_decoded, wm)
                l2_wm = L2_loss_wm(wm_decoded, wm)

                total_loss, myloss_img, myloss_wm = get_loss(img, img_wm, wm, wm_decoded)

                total_loss.backward()
                optimizer.step()


            #caculate losses_dic
            bae = get_BAE(wm.cpu(),wm_decoded.cpu())
            psnr = get_PSNR(img.cpu(), img_wm.cpu())
            ssim = get_SSIM(img, img_wm)


            losses_dic = {
                'total_loss'        : float(total_loss),
                'my_loss_img'       : float(myloss_img),
                'my_loss_wm'        : float(myloss_wm),
                'L1_loss_img'       : float(l1_img),
                'L2_loss_img'       : float(l2_img),
                'L1_loss_wm'        : float(l1_wm),
                'L2_loss_wm'        : float(l2_wm),
                'BAE'               : float(bae),
                'PSNR'              : float(psnr),
                'SSIM'              : float(ssim),
            }

            # save loss
            for loss_name, loss_val in losses_dic.items():
                losses_record[loss_name].update(loss_val)
            print_info(epoch, step, cfg.TRAIN.STEP_PER_EPOCH, losses_record)

            # # save checkpoint
            # if l1_img.item() == None or l1_img.item() > 10000:
            #     save_ckpt(cfg.TRAIN.RUNS_FOLDER, [epoch, step], model, optimizer)
            #     raise valueError('LOSS  ERROR')
        if epoch % 50 == 49:
            save_ckpt(cfg.TRAIN.RUNS_FOLDER, [epoch, cfg.TRAIN.STEP_PER_EPOCH], model, optimizer)


                #write losses after every epoch


        val_losses_record = defaultdict(AverageMeter)

        model.eval()
        logging.info('\nVAL EPOCH: {}'.format(epoch))
        for step, (img, _) in enumerate(val_img_DataLoder):


            img = img.to(cfg.TRAIN.DEVICE)
            wm = torch.Tensor(np.random.choice([0, 1], 
                (cfg.TRAIN.BATCH_SIZE, 1, cfg.DATA_SET.H_WM, cfg.DATA_SET.W_WM ))).to(cfg.TRAIN.DEVICE)

            cfg.Noiser.RANDOM_NUM = random.randint(0,4)

            with torch.no_grad():
                img_wm, img_noise, wm_decoded = model(img, wm)

                l1_img = L1_loss_img(img_wm, img)
                l2_img = L2_loss_img(img_wm, img)

                l1_wm = L1_loss_wm(wm_decoded, wm)
                l2_wm = L2_loss_wm(wm_decoded, wm)


                total_loss, myloss_img, myloss_wm = get_loss(img, img_wm, wm, wm_decoded)


            #caculate losses_dic
            bae = get_BAE(wm.cpu(),wm_decoded.cpu())
            psnr = get_PSNR(img.cpu(), img_wm.cpu())
            ssim = get_SSIM(img, img_wm)

            losses_dic = {
                'total_loss'        : float(total_loss),
                'my_loss_img'       : float(myloss_img),
                'my_loss_wm'        : float(myloss_wm),
                'L1_loss_img'       : float(l1_img),
                'L2_loss_img'       : float(l2_img),
                'L1_loss_wm'        : float(l1_wm),
                'L2_loss_wm'        : float(l2_wm),
                'BAE'               : float(bae),
                'PSNR'              : float(psnr),
                'SSIM'              : float(ssim),
            }

            for loss_name, loss_val in losses_dic.items():
                val_losses_record[loss_name].update(loss_val)
            print_info(epoch, step, cfg.VAL.STEP_PER_EPOCH , val_losses_record)

        save_imgs_wms(img.cpu(), img_wm.cpu(), img_noise.cpu(), wm.cpu(), wm_decoded.cpu(),epoch)

        # save_images(img, img_wm, epoch, 
        #     os.path.join(cfg.TRAIN.RUNS_FOLDER, 'images_wms'),
        #     resize_to = 128 )

        if not cfg.TRAIN.NO_SAVE:
            write_losses(os.path.join(cfg.TRAIN.RUNS_FOLDER,  cfg.TRAIN.NAME  + '_train.csv'), losses_record, epoch, 0)
            write_losses(os.path.join(cfg.TRAIN.RUNS_FOLDER,  cfg.TRAIN.NAME  + '_val.csv'), val_losses_record, epoch, 0)

        torch.cuda.empty_cache()




def print_info(epoch, step, set_pre_epoch, losses_record):

    if step % 10 == 0 :

        logging.info(
            'Epoch: {}/{} Step: {}/{}'.format(epoch, cfg.TRAIN.EPOCHS, step, set_pre_epoch ))
        # utils.log_progress(training_losses)
        logging.info('-' * 40)
        log_print_helper(losses_record,logging.info)
        logging.info('-' * 40)

def log_print_helper(losses_accu, log_or_print_func):
    max_len = max([len(loss_name) for loss_name in losses_accu])
    for loss_name, loss_value in losses_accu.items():
        log_or_print_func(loss_name.ljust(max_len + 4) + '{:.4f}'.format(loss_value.avg))

def write_losses(file_name, losses_accu, epoch, duration):
    with open(file_name, 'a', newline='') as csvfile:
        writer = csv.writer(csvfile)
        if epoch == 1:
            row_to_write = ['epoch'] + [loss_name.strip() for loss_name in losses_accu.keys()] + ['duration']
            writer.writerow(row_to_write)
        row_to_write = [epoch] + ['{:.4f}'.format(loss_avg.avg) for loss_avg in losses_accu.values()] + [
            '{:.0f}'.format(duration)]
        writer.writerow(row_to_write)


# save_images(image.cpu()[:8, :, :, :], encoded_images[:images_to_save, :, :, :].cpu(),
#                   epoch,
#                   os.path.join(this_run_folder, 'images'), resize_to=saved_images_size)





def get_BAE(wm, wm_decoded):
    wm_decoded_rounded = wm_decoded.detach().numpy().round().clip(0, 1)
    bae = np.sum(np.abs(wm_decoded_rounded - wm.detach().numpy())) / (cfg.TRAIN.BATCH_SIZE * wm.shape[2] * wm.shape[3])
    return bae


def save_imgs_wms(img, img_wm, img_noise, wm, wm_decoded,epoch):
    save_imgs(img, img_wm, img_noise, epoch)
    save_wms(wm, wm_decoded, epoch)



def save_imgs(img, img_wm, img_noise, epoch):
    img = img[: cfg.DATA_SET.SAVE_IMGS, :, :, :]
    img_wm = img_wm[: cfg.DATA_SET.SAVE_IMGS, :, :, :]
    img_noise = img_noise[: cfg.DATA_SET.SAVE_IMGS, :, :, :]

    img_r = img_wm.clone() - img.clone()
    img_r = img_r * 5
    # scale values to range [0, 1] from original range of [-1, 1]
    stacke_img = torch.cat([img, img_wm, img_noise, img_r], dim=0)
    stacke_img = torch.nn.functional.interpolate(stacke_img, size=cfg.DATA_SET.SAVE_IMGS_SIZE)


    filename = os.path.join(cfg.DATA_SET.SAVE_IMGS_DIR, 'epoch_{}.png'.format(epoch))

    torchvision.utils.save_image(stacke_img, filename, nrow=img.shape[0],
        padding=2, 
        normalize=True, 
        range=(-1,1), 
        scale_each=False, 
        pad_value=0)

def save_wms(wm, wm_decoded, epoch):

    wm = wm[: cfg.DATA_SET.SAVE_IMGS, :, :, :]
    wm_decoded = wm_decoded[: cfg.DATA_SET.SAVE_IMGS, :, :, :]
    wm_round =  wm_decoded.detach().numpy().round().clip(0, 1)
    wm_round = torch.from_numpy(wm_round) 
    stacke_wm = torch.cat([wm, wm_decoded, wm_round], dim=0)

    stacke_wm = torch.nn.functional.upsample_nearest(stacke_wm, size=None, scale_factor=cfg.DATA_SET.SAVE_WMS_SCALES)
    filename = os.path.join(cfg.DATA_SET.SAVE_WMS_DIR, 'epoch_{}.png'.format(epoch))

    torchvision.utils.save_image(stacke_wm, filename, nrow=wm.shape[0],
        padding=2, 
        normalize=True, 
        range=(0,1), 
        scale_each=False, 
        pad_value=0)

 
def get_PSNR(img, img_wm):

    avg_psnr = 0
    for i,j in zip(img,img_wm):

        mse = torch.nn.functional.mse_loss(i, j, reduce=None, reduction='mean')
        if mse < 1.0e-10:
            psnr = 100
        else:
            psnr =  10 * torch.log10(1 / mse)
        avg_psnr += psnr
        
    avg_psnr = avg_psnr / cfg.TRAIN.BATCH_SIZE
    return avg_psnr





 
def get_SSIM(img1, img2):
    losser = SSIM(data_range=1., channel=3).cuda()
    # losser.to(cfg.TRAIN.DEVICE)
    loss = losser(img1, img2).mean()


    return loss

def get_loss(img, img_wm, wm, wm_decoded):
    img_loss = get_img_loss(img, img_wm)
    wm_loss = get_wm_loss(wm, wm_decoded)
    total_loss = img_loss * cfg.MODEL.ENCODER_LOSS + wm_loss * cfg.MODEL.DECODER_LOSS

    return total_loss, img_loss, wm_loss

def get_img_loss(img, img_wm):

    if cfg.MODEL.IMG_LOSS_NAME == 'SSIMLoss':
        loss_fun = SSIM(data_range=1., channel=3).cuda()
        img_loss = -1 * loss_fun(img_wm, img).mean()

    else:
        loss_fun = eval('nn.'+ cfg.MODEL.IMG_LOSS_NAME)()
        loss_fun.cuda()
        img_loss = loss_fun(img, img_wm)
    return img_loss

def get_wm_loss(wm, wm_decoded):

    loss_fun = eval('nn.'+ cfg.MODEL.WM_LOSS_NAME)()
    loss_fun.cuda()

    if cfg.MODEL.WM_LOSS_NAME == 'CrossEntropyLoss':

        wm_ones_p = wm_decoded.reshape(wm_decoded.size(0),-1).unsqueeze(1)
        wm_zeros_p =torch.ones_like(wm_ones_p)-wm_ones_p
        wm_input = torch.cat([wm_zeros_p,wm_ones_p],dim = 1)
        wm_target = wm.reshape(wm.size(0),-1).long()
    else:
        wm_input = wm
        wm_target = wm_decoded

    wm_loss  = loss_fun(wm_input, wm_target)

    return wm_loss