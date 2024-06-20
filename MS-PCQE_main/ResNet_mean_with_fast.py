import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.utils.model_zoo as model_zoo
from pytorchvideo.models import create_slowfast
from vit_pytorch import SimpleViT
from vit_pytorch import SimpleViT_double
import open3d as o3d
import numpy as np
from convGRU import ConvGRU



def pc_normalize(pc):
    centroid = np.mean(pc, axis=0)
    pc = pc - centroid
    m = np.max(np.sqrt(np.sum(pc**2, axis=1)))
    pc = pc / m
    return pc



def global_std_pool2d(x):
    """2D global standard variation pooling"""
    return torch.std(x.view(x.size()[0], x.size()[1], -1, 1),
                     dim=2, keepdim=True)


__all__ = ['ResNet', 'resnet18', 'resnet34', 'resnet50', 'resnet101',
           'resnet152', 'resnext50_32x4d', 'resnext101_32x8d',
           'wide_resnet50_2', 'wide_resnet101_2']

model_urls = {
    'resnet18': 'https://download.pytorch.org/models/resnet18-5c106cde.pth',
    'resnet34': 'https://download.pytorch.org/models/resnet34-333f7ec4.pth',
    'resnet50': 'https://download.pytorch.org/models/resnet50-19c8e357.pth',
    'resnet101': 'https://download.pytorch.org/models/resnet101-5d3b4d8f.pth',
    'resnet152': 'https://download.pytorch.org/models/resnet152-b121ed2d.pth',
    'resnext50_32x4d': 'https://download.pytorch.org/models/resnext50_32x4d-7cdf4587.pth',
    'resnext101_32x8d': 'https://download.pytorch.org/models/resnext101_32x8d-8ba56ff5.pth',
    'wide_resnet50_2': 'https://download.pytorch.org/models/wide_resnet50_2-95faca4d.pth',
    'wide_resnet101_2': 'https://download.pytorch.org/models/wide_resnet101_2-32ee1156.pth',
}

def conv3x3(in_planes, out_planes, stride=1, groups=1, dilation=1):
    """3x3 convolution with padding"""
    return nn.Conv2d(in_planes, out_planes, kernel_size=3, stride=stride,
                     padding=dilation, groups=groups, bias=False, dilation=dilation)


def conv1x1(in_planes, out_planes, stride=1):
    """1x1 convolution"""
    return nn.Conv2d(in_planes, out_planes, kernel_size=1, stride=stride, bias=False)


class BasicBlock(nn.Module):
    expansion = 1
    __constants__ = ['downsample']

    def __init__(self, inplanes, planes, stride=1, downsample=None, groups=1,
                 base_width=64, dilation=1, norm_layer=None):
        super(BasicBlock, self).__init__()
        if norm_layer is None:
            norm_layer = nn.BatchNorm2d
        if groups != 1 or base_width != 64:
            raise ValueError('BasicBlock only supports groups=1 and base_width=64')
        if dilation > 1:
            raise NotImplementedError("Dilation > 1 not supported in BasicBlock")
        # Both self.conv1 and self.downsample layers downsample the input when stride != 1
        self.conv1 = conv3x3(inplanes, planes, stride)
        self.bn1 = norm_layer(planes)
        self.relu = nn.ReLU(inplace=True)
        self.conv2 = conv3x3(planes, planes)
        self.bn2 = norm_layer(planes)
        self.downsample = downsample
        self.stride = stride

    def forward(self, x):
        identity = x

        out = self.conv1(x)
        out = self.bn1(out)
        out = self.relu(out)

        out = self.conv2(out)
        out = self.bn2(out)

        if self.downsample is not None:
            identity = self.downsample(x)

        out += identity
        out = self.relu(out)

        return out


class Bottleneck(nn.Module):
    expansion = 4
    __constants__ = ['downsample']

    def __init__(self, inplanes, planes, stride=1, downsample=None, groups=1,
                 base_width=64, dilation=1, norm_layer=None):
        super(Bottleneck, self).__init__()
        if norm_layer is None:
            norm_layer = nn.BatchNorm2d
        width = int(planes * (base_width / 64.)) * groups
        # Both self.conv2 and self.downsample layers downsample the input when stride != 1
        self.conv1 = conv1x1(inplanes, width)
        self.bn1 = norm_layer(width)
        self.conv2 = conv3x3(width, width, stride, groups, dilation)
        self.bn2 = norm_layer(width)
        self.conv3 = conv1x1(width, planes * self.expansion)
        self.bn3 = norm_layer(planes * self.expansion)
        self.relu = nn.ReLU(inplace=True)
        self.downsample = downsample
        self.stride = stride

    def forward(self, x):
        identity = x

        out = self.conv1(x)
        out = self.bn1(out)
        out = self.relu(out)

        out = self.conv2(out)
        out = self.bn2(out)
        out = self.relu(out)

        out = self.conv3(out)
        out = self.bn3(out)

        if self.downsample is not None:
            identity = self.downsample(x)

        out += identity
        out = self.relu(out)

        return out


class ResNet(nn.Module):

    def __init__(self, block, layers, num_classes=1000, zero_init_residual=False,
                 groups=1, width_per_group=64, replace_stride_with_dilation=None,
                 norm_layer=None):
        super(ResNet, self).__init__()
        if norm_layer is None:
            norm_layer = nn.BatchNorm2d
        self._norm_layer = norm_layer

        self.inplanes = 64
        self.dilation = 1
        if replace_stride_with_dilation is None:
            # each element in the tuple indicates if we should replace
            # the 2x2 stride with a dilated convolution instead
            replace_stride_with_dilation = [False, False, False]
        if len(replace_stride_with_dilation) != 3:
            raise ValueError("replace_stride_with_dilation should be None "
                             "or a 3-element tuple, got {}".format(replace_stride_with_dilation))


########################################################################################################################

        height = width = 128
        channels = 64
        hidden_dim = [32]
        kernel_size = (3, 3)  # kernel size for two stacked hidden layer
        num_layers = 1  # number of stacked hidden layer
        self.convgru1 = ConvGRU(input_size=(height, width),
                        input_dim=channels,
                        hidden_dim=hidden_dim,
                        kernel_size=kernel_size,
                        num_layers=num_layers,
                        dtype= torch.cuda.FloatTensor,
                        batch_first=True,
                        bias=True,
                        return_all_layers=False,
                        v=1)

        height = width = 64
        channels = 128
        hidden_dim = [32]
        kernel_size = (3, 3)  # kernel size for two stacked hidden layer
        num_layers = 1  # number of stacked hidden layer
        self.convgru2 = ConvGRU(input_size=(height, width),
                        input_dim=channels,
                        hidden_dim=hidden_dim,
                        kernel_size=kernel_size,
                        num_layers=num_layers,
                        dtype= torch.cuda.FloatTensor,
                        batch_first=True,
                        bias=True,
                        return_all_layers=False,
                        v=1)

        height = width = 32
        channels = 256
        hidden_dim = [32]
        kernel_size = (3, 3)  # kernel size for two stacked hidden layer
        num_layers = 1  # number of stacked hidden layer
        self.convgru3 = ConvGRU(input_size=(height, width),
                        input_dim=channels,
                        hidden_dim=hidden_dim,
                        kernel_size=kernel_size,
                        num_layers=num_layers,
                        dtype= torch.cuda.FloatTensor,
                        batch_first=True,
                        bias=True,
                        return_all_layers=False,
                        v=1)

        height = width = 16
        channels = 512
        hidden_dim = [32]
        kernel_size = (3, 3)  # kernel size for two stacked hidden layer
        num_layers = 1  # number of stacked hidden layer
        self.convgru4 = ConvGRU(input_size=(height, width),
                        input_dim=channels,
                        hidden_dim=hidden_dim,
                        kernel_size=kernel_size,
                        num_layers=num_layers,
                        dtype= torch.cuda.FloatTensor,
                        batch_first=True,
                        bias=True,
                        return_all_layers=False,
                        v=1)



########################################################################################################################

        self.conv_z1_ref1 = SimpleViT(
            image_size=128,
            patch_size=16,
            num_classes=32,

            dim=64,
            depth=2,
            heads=2,
            mlp_dim=16,

            channels=32  # 3
        )



        self.conv_z1_ref2 = SimpleViT(
            image_size=64,
            patch_size=8,
            num_classes=32,

            dim=64,
            depth=2,
            heads=2,
            mlp_dim=16,

            channels=32  # 3
        )


        self.conv_z1_ref3 = SimpleViT(
            image_size=32,
            patch_size=4,
            num_classes=32,

            dim=64,
            depth=2,
            heads=2,
            mlp_dim=16,

            channels=32  # 3
        )


        self.conv_z1_ref4 = SimpleViT(
            image_size=16,
            patch_size=2,
            num_classes=32,

            dim=64,
            depth=2,
            heads=2,
            mlp_dim=16,

            channels=32  # 3
        )





########################################################################################################################

        self.avgpool_blind = nn.AdaptiveAvgPool2d((1,1))
        self.quality_blind1 = nn.Sequential(
            nn.Linear(512, 128),
            nn.Dropout(0.5))
        self.quality_blind2 = nn.Linear(128, 1)


########################################################################################################################

        self.conv_z_ref1 = SimpleViT_double(
            image_size=128,
            patch_size=16,
            num_classes=32,

            dim=64,
            depth=2,
            heads=2,
            mlp_dim=16,

            channels=32  # 3
        )



        self.conv_z_ref2 = SimpleViT_double(
            image_size=64,
            patch_size=8,
            num_classes=32,

            dim=64,
            depth=2,
            heads=2,
            mlp_dim=16,

            channels=32  # 3
        )


        self.conv_z_ref3 = SimpleViT_double(
            image_size=32,
            patch_size=4,
            num_classes=32,

            dim=64,
            depth=2,
            heads=2,
            mlp_dim=16,

            channels=32  # 3
        )


        self.conv_z_ref4 = SimpleViT_double(
            image_size=16,
            patch_size=2,
            num_classes=32,

            dim=64,
            depth=2,
            heads=2,
            mlp_dim=16,

            channels=32  # 3
        )



        self.quality_img_ref1 = nn.Sequential(
            nn.Linear(32*16, 32*4),
            nn.Dropout(0.5))
        self.quality_img_ref2 = nn.Linear(128, 1)



########################################################################################################################


        self.avgpool = nn.AdaptiveAvgPool2d((1, 1))

########################################################################################################################

        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='relu')
            elif isinstance(m, (nn.BatchNorm2d, nn.GroupNorm)):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)

        # Zero-initialize the last BN in each residual branch,
        # so that the residual branch starts with zeros, and each residual block behaves like an identity.
        # This improves the model by 0.2~0.3% according to https://arxiv.org/abs/1706.02677
        if zero_init_residual:
            for m in self.modules():
                if isinstance(m, Bottleneck):
                    nn.init.constant_(m.bn3.weight, 0)
                elif isinstance(m, BasicBlock):
                    nn.init.constant_(m.bn2.weight, 0)


########################################################################################################################

        self.groups = groups
        self.base_width = width_per_group
        self.conv1 = nn.Conv2d(3, self.inplanes, kernel_size=7, stride=2, padding=3,
                               bias=False)
        self.bn1 = norm_layer(self.inplanes)
        self.relu = nn.ReLU(inplace=True)
        self.maxpool = nn.MaxPool2d(kernel_size=3, stride=2, padding=1)
        self.layer1 = self._make_layer(block, 64, layers[0])
        self.layer2 = self._make_layer(block, 128, layers[1], stride=2,
                                       dilate=replace_stride_with_dilation[0])
        self.layer3 = self._make_layer(block, 256, layers[2], stride=2,
                                       dilate=replace_stride_with_dilation[1])
        self.layer4 = self._make_layer(block, 512, layers[3], stride=2,
                                       dilate=replace_stride_with_dilation[2])



########################################################################################################################

    def _make_layer(self, block, planes, blocks, stride=1, dilate=False):
        norm_layer = self._norm_layer
        downsample = None
        previous_dilation = self.dilation
        if dilate:
            self.dilation *= stride
            stride = 1
        if stride != 1 or self.inplanes != planes * block.expansion:
            downsample = nn.Sequential(
                conv1x1(self.inplanes, planes * block.expansion, stride),
                norm_layer(planes * block.expansion),
            )

        layers = []
        layers.append(block(self.inplanes, planes, stride, downsample, self.groups,
                            self.base_width, previous_dilation, norm_layer))
        self.inplanes = planes * block.expansion
        for _ in range(1, blocks):
            layers.append(block(self.inplanes, planes, groups=self.groups,
                                base_width=self.base_width, dilation=self.dilation,
                                norm_layer=norm_layer))

        return nn.Sequential(*layers)

    def quality_pred(self,in_channels,middle_channels,out_channels):
        regression_block = nn.Sequential(
            nn.Linear(in_channels, middle_channels),
            nn.Linear(middle_channels, out_channels),
        )

        return regression_block

    def hyper_structure1(self,in_channels,out_channels):

        hyper_block = nn.Sequential(
            nn.Conv2d(in_channels,in_channels//4,kernel_size=1,stride=1, padding=0,bias=False),
            nn.Conv2d(in_channels//4,in_channels//4,kernel_size=3,stride=1, padding=1,bias=False),
            nn.Conv2d(in_channels//4,out_channels,kernel_size=1,stride=1, padding=0,bias=False),
        )

        return hyper_block

    def hyper_structure2(self,in_channels,out_channels):
        hyper_block = nn.Sequential(
            nn.Conv2d(in_channels,in_channels//4,kernel_size=1,stride=1, padding=0,bias=False),
            nn.Conv2d(in_channels//4,in_channels//4,kernel_size=3,stride=2, padding=1,bias=False),
            nn.Conv2d(in_channels//4,out_channels,kernel_size=1,stride=1, padding=0,bias=False),
        )

        return hyper_block


########################################################################################################################


    def forward(self, frames_dir_10_video, frames_dir_05_video, frames_dir_10_video_mask, frames_dir_05_video_mask, mode_idx):

        if mode_idx == 0 or mode_idx == 1:

            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            frames_dir_10_video = frames_dir_10_video.to(device)
            frames_dir_05_video = frames_dir_05_video.to(device)
            frames_dir_10_video_mask = frames_dir_10_video_mask.to(device)
            frames_dir_05_video_mask = frames_dir_05_video_mask.to(device)

            x_size = frames_dir_10_video.shape
            x_mask_size = frames_dir_10_video_mask.shape
            x_10 = frames_dir_10_video.view(-1, x_size[2], x_size[3], x_size[4])
            x_10_mask = frames_dir_10_video_mask.view(-1, x_mask_size[2], x_mask_size[3], x_mask_size[4])
            x_05 = frames_dir_05_video.view(-1, x_size[2], x_size[3], x_size[4])
            x_05_mask = frames_dir_05_video_mask.view(-1, x_mask_size[2], x_mask_size[3], x_mask_size[4])

            x = self.conv1(x_10)
            x = self.bn1(x)
            x = self.relu(x)
            x = self.maxpool(x)
            x_image1_10 = self.layer1(x)
            x_image2_10 = self.layer2(x_image1_10)
            x_image3_10 = self.layer3(x_image2_10)
            x_image4_10 = self.layer4(x_image3_10)


            x = self.conv1(x_05)
            x = self.bn1(x)
            x = self.relu(x)
            x = self.maxpool(x)
            x_image1_05 = self.layer1(x)
            x_image2_05 = self.layer2(x_image1_05)
            x_image3_05 = self.layer3(x_image2_05)
            x_image4_05 = self.layer4(x_image3_05)


            layer_output_list, last_state_list = self.convgru1(x_image1_10.unsqueeze(1), x_image1_05.unsqueeze(1))
            x_image1_10_gru = layer_output_list[0].squeeze(1)
            layer_output_list, last_state_list = self.convgru1(x_image1_05.unsqueeze(1), x_image1_10.unsqueeze(1))
            x_image1_05_gru = layer_output_list[0].squeeze(1)
            mask_scaled = torch.nn.functional.interpolate(x_10_mask, scale_factor=1 / 4).repeat(1,x_image1_10_gru.size(1),1,1)
            z_ref1_10 = self.conv_z_ref1(x_image1_10_gru, mask_scaled)
            z1_ref1_10 = self.conv_z1_ref1(x_image1_10_gru)
            z_ref1_10 = torch.cat((z_ref1_10 , z1_ref1_10), dim=1)
            mask_scaled = torch.nn.functional.interpolate(x_05_mask, scale_factor=1 / 4).repeat(1,x_image1_05_gru.size(1),1,1)
            z_ref1_05 = self.conv_z_ref1(x_image1_05_gru, mask_scaled)
            z1_ref1_05 = self.conv_z1_ref1(x_image1_05_gru)
            z_ref1_05 = torch.cat((z_ref1_05 , z1_ref1_05), dim=1)


            layer_output_list, last_state_list = self.convgru2(x_image2_10.unsqueeze(1), x_image2_05.unsqueeze(1))
            x_image2_10_gru = layer_output_list[0].squeeze(1)
            layer_output_list, last_state_list = self.convgru2(x_image2_05.unsqueeze(1), x_image2_10.unsqueeze(1))
            x_image2_05_gru = layer_output_list[0].squeeze(1)
            mask_scaled = torch.nn.functional.interpolate(x_10_mask, scale_factor=1 / 8).repeat(1,x_image2_10_gru.size(1),1,1)
            z_ref2_10 = self.conv_z_ref2(x_image2_10_gru, mask_scaled)
            z1_ref2_10 = self.conv_z1_ref2(x_image2_10_gru)
            z_ref2_10 = torch.cat((z_ref2_10 , z1_ref2_10), dim=1)
            mask_scaled = torch.nn.functional.interpolate(x_05_mask, scale_factor=1 / 8).repeat(1,x_image2_05_gru.size(1),1,1)
            z_ref2_05 = self.conv_z_ref2(x_image2_05_gru, mask_scaled)
            z1_ref2_05 = self.conv_z1_ref2(x_image2_05_gru)
            z_ref2_05 = torch.cat((z_ref2_05 , z1_ref2_05), dim=1)




            layer_output_list, last_state_list = self.convgru3(x_image3_10.unsqueeze(1), x_image3_05.unsqueeze(1))
            x_image3_10_gru = layer_output_list[0].squeeze(1)
            layer_output_list, last_state_list = self.convgru3(x_image3_05.unsqueeze(1), x_image3_10.unsqueeze(1))
            x_image3_05_gru = layer_output_list[0].squeeze(1)
            mask_scaled = torch.nn.functional.interpolate(x_10_mask, scale_factor=1 / 16).repeat(1,x_image3_10_gru.size(1),1,1)
            z_ref3_10 = self.conv_z_ref3(x_image3_10_gru, mask_scaled)
            z1_ref3_10 = self.conv_z1_ref3(x_image3_10_gru)
            z_ref3_10 = torch.cat((z_ref3_10 , z1_ref3_10), dim=1)
            mask_scaled = torch.nn.functional.interpolate(x_05_mask, scale_factor=1 / 16).repeat(1,x_image3_05_gru.size(1),1,1)
            z_ref3_05 = self.conv_z_ref3(x_image3_05_gru, mask_scaled)
            z1_ref3_05 = self.conv_z1_ref3(x_image3_05_gru)
            z_ref3_05 = torch.cat((z_ref3_05 , z1_ref3_05), dim=1)




            layer_output_list, last_state_list = self.convgru4(x_image4_10.unsqueeze(1), x_image4_05.unsqueeze(1))
            x_image4_10_gru = layer_output_list[0].squeeze(1)
            layer_output_list, last_state_list = self.convgru4(x_image4_05.unsqueeze(1), x_image4_10.unsqueeze(1))
            x_image4_05_gru = layer_output_list[0].squeeze(1)
            mask_scaled = torch.nn.functional.interpolate(x_10_mask, scale_factor=1 / 32).repeat(1,x_image4_10_gru.size(1),1,1)
            z_ref4_10 = self.conv_z_ref4(x_image4_10_gru, mask_scaled)
            z1_ref4_10 = self.conv_z1_ref4(x_image4_10_gru)
            z_ref4_10 = torch.cat((z_ref4_10 , z1_ref4_10), dim=1)
            mask_scaled = torch.nn.functional.interpolate(x_05_mask, scale_factor=1 / 32).repeat(1,x_image4_05_gru.size(1),1,1)
            z_ref4_05 = self.conv_z_ref4(x_image4_05_gru, mask_scaled)
            z1_ref4_05 = self.conv_z1_ref4(x_image4_05_gru)
            z_ref4_05 = torch.cat((z_ref4_05 , z1_ref4_05), dim=1)




            y_mid_avg = torch.cat((z_ref1_10, z_ref1_05, z_ref2_10, z_ref2_05, z_ref3_10, z_ref3_05, z_ref4_10, z_ref4_05), dim=1)



            y_mid_avg = self.quality_img_ref1(y_mid_avg)
            y_mid_avg = self.quality_img_ref2(y_mid_avg)
            y_mid_avg = y_mid_avg.view(x_size[0], x_size[1])
            y_mid_blind = torch.mean(y_mid_avg, dim=1)

            return y_mid_blind




def _resnet(arch, block, layers, pretrained, progress, **kwargs):
    model = ResNet(block, layers, **kwargs)
    if pretrained:
        state_dict = load_state_dict_from_url(model_urls[arch],
                                              progress=progress)
        model.load_state_dict(state_dict)
    return model


def resnet18(pretrained=False, progress=True, **kwargs):
    r"""ResNet-18 model from
    `"Deep Residual Learning for Image Recognition" <https://arxiv.org/pdf/1512.03385.pdf>`_
    Args:
        pretrained (bool): If True, returns a model pre-trained on ImageNet
        progress (bool): If True, displays a progress bar of the download to stderr
    """
    # return _resnet('resnet18', BasicBlock, [2, 2, 2, 2], pretrained, progress,
    #                **kwargs)

    model = ResNet(BasicBlock, [2, 2, 2, 2], **kwargs)
    if pretrained:
        # model.load_state_dict(model_zoo.load_url(model_urls['resnet50']))
        model_dict = model.state_dict()
        pre_train_model = model_zoo.load_url(model_urls['resnet18'])
        pre_train_model = {k:v for k,v in pre_train_model.items() if k in model_dict}
        model_dict.update(pre_train_model)
        model.load_state_dict(model_dict)

    return model



def resnet34(pretrained=False, progress=True, **kwargs):
    r"""ResNet-34 model from
    `"Deep Residual Learning for Image Recognition" <https://arxiv.org/pdf/1512.03385.pdf>`_
    Args:
        pretrained (bool): If True, returns a model pre-trained on ImageNet
        progress (bool): If True, displays a progress bar of the download to stderr
    """
    model = ResNet(BasicBlock, [3, 4, 6, 3], **kwargs)
    if pretrained:
        # model.load_state_dict(model_zoo.load_url(model_urls['resnet50']))
        model_dict = model.state_dict()
        pre_train_model = model_zoo.load_url(model_urls['resnet34'])
        pre_train_model = {k:v for k,v in pre_train_model.items() if k in model_dict}
        model_dict.update(pre_train_model)
        model.load_state_dict(model_dict)

    return model


def resnet50(pretrained=False, progress=True, **kwargs):
    r"""ResNet-50 model from
    `"Deep Residual Learning for Image Recognition" <https://arxiv.org/pdf/1512.03385.pdf>`_
    Args:
        pretrained (bool): If True, returns a model pre-trained on ImageNet
        progress (bool): If True, displays a progress bar of the download to stderr
    """
    model = ResNet(Bottleneck, [3, 4, 6, 3], **kwargs)
    # input = torch.randn(1, 3, 224, 224)
    # flops, params = profile(model, inputs=(input, ))
    # print('The flops is {:.4f}, and the params is {:.4f}'.format(flops/10e9, params/10e6))
    if pretrained:
        # model.load_state_dict(model_zoo.load_url(model_urls['resnet50']))
        model_dict = model.state_dict()
        pre_train_model = model_zoo.load_url(model_urls['resnet50'])
        # pre_train_model = torch.load('./base_ckpts/ResNet_mean_std_MTL_epoch_30_accu_0.963589.pth')
        # print (pre_train_model.items())
        pre_train_model = {k:v for k,v in pre_train_model.items() if k in model_dict and not ('branch_' in k)}
        model_dict.update(pre_train_model)
        model.load_state_dict(model_dict)
        print ('load the pretrained model, done！')

    return model


def resnet101(pretrained=False, progress=True, **kwargs):
    r"""ResNet-101 model from
    `"Deep Residual Learning for Image Recognition" <https://arxiv.org/pdf/1512.03385.pdf>`_
    Args:
        pretrained (bool): If True, returns a model pre-trained on ImageNet
        progress (bool): If True, displays a progress bar of the download to stderr
    """
    # return _resnet('resnet101', Bottleneck, [3, 4, 23, 3], pretrained, progress,
    #                **kwargs)
    model = ResNet(Bottleneck, [3, 4, 23, 3], **kwargs)
    if pretrained:
        model_dict = model.state_dict()
        pre_train_model = model_zoo.load_url(model_urls['resnet101'])
        pre_train_model = {k:v for k,v in pre_train_model.items() if k in model_dict}
        model_dict.update(pre_train_model)
        model.load_state_dict(model_dict)
    return model


def resnet152(pretrained=False, progress=True, **kwargs):
    r"""ResNet-152 model from
    `"Deep Residual Learning for Image Recognition" <https://arxiv.org/pdf/1512.03385.pdf>`_
    Args:
        pretrained (bool): If True, returns a model pre-trained on ImageNet
        progress (bool): If True, displays a progress bar of the download to stderr
    """
    # return _resnet('resnet152', Bottleneck, [3, 8, 36, 3], pretrained, progress,
    #                **kwargs)
    model = ResNet(Bottleneck, [3, 8, 36, 3], **kwargs)
    if pretrained:
        model_dict = model.state_dict()
        pre_train_model = model_zoo.load_url(model_urls['resnet152'])
        pre_train_model = {k:v for k,v in pre_train_model.items() if k in model_dict}
        model_dict.update(pre_train_model)
        model.load_state_dict(model_dict)
    return model


def resnext50_32x4d(pretrained=False, progress=True, **kwargs):
    r"""ResNeXt-50 32x4d model from
    `"Aggregated Residual Transformation for Deep Neural Networks" <https://arxiv.org/pdf/1611.05431.pdf>`_
    Args:
        pretrained (bool): If True, returns a model pre-trained on ImageNet
        progress (bool): If True, displays a progress bar of the download to stderr
    """
    kwargs['groups'] = 32
    kwargs['width_per_group'] = 4
    #return _resnet('resnext50_32x4d', Bottleneck, [3, 4, 6, 3],
       #            pretrained, progress, **kwargs)
    model = ResNet(Bottleneck, [3, 4, 6, 3],
                   pretrained, progress, **kwargs)
    if pretrained:
        model_dict = model.state_dict()
        pre_train_model = model_zoo.load_url(model_urls['resnext50_32x4d'])
        pre_train_model = {k:v for k,v in pre_train_model.items() if k in model_dict}
        model_dict.update(pre_train_model)
        model.load_state_dict(model_dict)
    return model


def resnext101_32x8d(pretrained=False, progress=True, **kwargs):
    r"""ResNeXt-101 32x8d model from
    `"Aggregated Residual Transformation for Deep Neural Networks" <https://arxiv.org/pdf/1611.05431.pdf>`_
    Args:
        pretrained (bool): If True, returns a model pre-trained on ImageNet
        progress (bool): If True, displays a progress bar of the download to stderr
    """
    kwargs['groups'] = 32
    kwargs['width_per_group'] = 8
    # return _resnet('resnext101_32x8d', Bottleneck, [3, 4, 23, 3],
    #                pretrained, progress, **kwargs)
    model = ResNet(Bottleneck, [3, 4, 23, 3],
                   pretrained, progress, **kwargs)
    if pretrained:
        model_dict = model.state_dict()
        pre_train_model = model_zoo.load_url(model_urls['resnext101_32x8d'])
        pre_train_model = {k:v for k,v in pre_train_model.items() if k in model_dict}
        model_dict.update(pre_train_model)
        model.load_state_dict(model_dict)
    return model


def wide_resnet50_2(pretrained=False, progress=True, **kwargs):
    r"""Wide ResNet-50-2 model from
    `"Wide Residual Networks" <https://arxiv.org/pdf/1605.07146.pdf>`_
    The model is the same as ResNet except for the bottleneck number of channels
    which is twice larger in every block. The number of channels in outer 1x1
    convolutions is the same, e.g. last block in ResNet-50 has 2048-512-2048
    channels, and in Wide ResNet-50-2 has 2048-1024-2048.
    Args:
        pretrained (bool): If True, returns a model pre-trained on ImageNet
        progress (bool): If True, displays a progress bar of the download to stderr
    """
    kwargs['width_per_group'] = 64 * 2
    return _resnet('wide_resnet50_2', Bottleneck, [3, 4, 6, 3],
                   pretrained, progress, **kwargs)


def wide_resnet101_2(pretrained=False, progress=True, **kwargs):
    r"""Wide ResNet-101-2 model from
    `"Wide Residual Networks" <https://arxiv.org/pdf/1605.07146.pdf>`_
    The model is the same as ResNet except for the bottleneck number of channels
    which is twice larger in every block. The number of channels in outer 1x1
    convolutions is the same, e.g. last block in ResNet-50 has 2048-512-2048
    channels, and in Wide ResNet-50-2 has 2048-1024-2048.
    Args:
        pretrained (bool): If True, returns a model pre-trained on ImageNet
        progress (bool): If True, displays a progress bar of the download to stderr
    """
    kwargs['width_per_group'] = 64 * 2
    return _resnet('wide_resnet101_2', Bottleneck, [3, 4, 23, 3],
                   pretrained, progress, **kwargs)





if __name__ == '__main__':
    device = torch.device('cuda')
    net = resnet50(pretrained=True)
    net.to(device)
    video = torch.randn(1,4,3,448,448).cuda()
    features = torch.randn(1,4,2048).cuda()
    print(net(video,features))
    