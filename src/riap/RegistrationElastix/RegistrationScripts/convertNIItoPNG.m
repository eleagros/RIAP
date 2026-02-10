function convertNIItoPNG(iNIIFileName,outPNGFileName,interpMode)
NII = load_nii(iNIIFileName);
img = single(NII.img);
img = imrotate(transpose(img),180); % compensate for matlab row/column inversion
if interpMode < 2
    img = (img-min(img(:)))/(max(img(:))-min(img(:))); % [0,1]
    if interpMode
        img(img>=.5) = 1;
        img(img< .5) = 0;
    end
    img = 255.*img; % [0,255]
else
    img = round(img);
end
img = uint8(img); % cast to uint8 Data Type
imwrite(img,outPNGFileName,'png');