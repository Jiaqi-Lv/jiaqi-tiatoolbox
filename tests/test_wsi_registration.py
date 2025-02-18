"""Test WSI Registration."""
from pathlib import Path

import cv2
import numpy as np
import pytest

from tiatoolbox.tools.registration.wsi_registration import (
    AffineWSITransformer,
    DFBRegister,
    apply_affine_transformation,
    apply_bspline_transform,
    estimate_bspline_transform,
    match_histograms,
    prealignment,
)
from tiatoolbox.utils import imread
from tiatoolbox.utils.metrics import dice
from tiatoolbox.wsicore.wsireader import WSIReader

RNG = np.random.default_rng()  # Numpy Random Generator


def test_extract_features(dfbr_features: Path) -> None:
    """Test for CNN based feature extraction function."""
    # dfbr (deep feature based registration).
    dfbr = DFBRegister()
    fixed_img = np.repeat(
        np.expand_dims(
            np.repeat(
                np.expand_dims(np.arange(0, 64, 1, dtype=np.uint8), axis=1),
                64,
                axis=1,
            ),
            axis=2,
        ),
        3,
        axis=2,
    )
    output = dfbr.extract_features(fixed_img, fixed_img)
    pool3_feat = output["block3_pool"][0, :].detach().numpy()
    pool4_feat = output["block4_pool"][0, :].detach().numpy()
    pool5_feat = output["block5_pool"][0, :].detach().numpy()

    _pool3_feat, _pool4_feat, _pool5_feat = np.load(
        str(dfbr_features),
        allow_pickle=True,
    )
    assert np.mean(np.abs(pool3_feat - _pool3_feat)) < 1.0e-4
    assert np.mean(np.abs(pool4_feat - _pool4_feat)) < 1.0e-4
    assert np.mean(np.abs(pool5_feat - _pool5_feat)) < 1.0e-4


def test_feature_mapping(fixed_image: Path, moving_image: Path) -> None:
    """Test for CNN based feature matching function."""
    fixed_img = imread(fixed_image)
    moving_img = imread(moving_image)
    pre_transform = np.array([[-1, 0, 337.8], [0, -1, 767.7], [0, 0, 1]])
    moving_img = cv2.warpAffine(
        moving_img,
        pre_transform[0:-1][:],
        fixed_img.shape[:2][::-1],
    )

    dfbr = DFBRegister()
    features = dfbr.extract_features(fixed_img, moving_img)
    fixed_matched_points, moving_matched_points, _ = dfbr.feature_mapping(features)
    output = dfbr.estimate_affine_transform(fixed_matched_points, moving_matched_points)
    expected = np.array(
        [[0.98843, 0.00184, 1.75437], [-0.00472, 0.96973, 5.38854], [0, 0, 1]],
    )
    assert np.mean(output - expected) < 1.0e-6


def test_dfbr_features() -> None:
    """Test for feature input to feature_mapping function."""
    dfbr = DFBRegister()
    fixed_img = np.repeat(
        np.expand_dims(
            np.repeat(
                np.expand_dims(np.arange(0, 64, 1, dtype=np.uint8), axis=1),
                64,
                axis=1,
            ),
            axis=2,
        ),
        3,
        axis=2,
    )
    features = dfbr.extract_features(fixed_img, fixed_img)

    del features["block5_pool"]
    with pytest.raises(
        ValueError,
        match=r".*The feature mapping step expects 3 blocks of features.*",
    ):
        _, _, _ = dfbr.feature_mapping(features)


def test_prealignment_mask() -> None:
    """Test for mask inputs to prealignment function."""
    fixed_img = RNG.random((10, 10))
    moving_img = RNG.random((10, 10))
    no_fixed_mask = np.zeros(shape=fixed_img.shape, dtype=int)
    no_moving_mask = np.zeros(shape=moving_img.shape, dtype=int)
    with pytest.raises(ValueError, match=r".*The foreground is missing in the mask.*"):
        _ = prealignment(fixed_img, moving_img, no_fixed_mask, no_moving_mask)


def test_prealignment_input_shape() -> None:
    """Test for inputs to prealignment function."""
    fixed_img = RNG.random((10, 10))
    moving_img = RNG.random((15, 10))
    fixed_mask = RNG.choice([0, 1], size=(15, 10))
    moving_mask = RNG.choice([0, 1], size=(10, 10))

    with pytest.raises(
        ValueError,
        match=r".*Mismatch of shape between image and its corresponding mask.*",
    ):
        _ = prealignment(fixed_img, moving_img, fixed_mask, moving_mask)


def test_prealignment_rotation_step() -> None:
    """Test for rotation step input to prealignment function."""
    fixed_img = RNG.random((10, 10))
    moving_img = RNG.random((10, 10))
    fixed_mask = RNG.choice([0, 1], size=(10, 10))
    moving_mask = RNG.choice([0, 1], size=(10, 10))

    with pytest.raises(
        ValueError,
        match=r".*Please select the rotation step in between 10 and 20.*",
    ):
        _ = prealignment(
            fixed_img,
            moving_img,
            fixed_mask,
            moving_mask,
            rotation_step=9,
        )

    with pytest.raises(
        ValueError,
        match=r".*Please select the rotation step in between 10 and 20.*",
    ):
        _ = prealignment(
            fixed_img,
            moving_img,
            fixed_mask,
            moving_mask,
            rotation_step=21,
        )


def test_prealignment_output(
    fixed_image: Path,
    moving_image: Path,
    fixed_mask: Path,
    moving_mask: Path,
) -> None:
    """Test for prealignment of an image pair."""
    fixed_img = imread(fixed_image)
    moving_img = imread(moving_image)
    fixed_mask = imread(fixed_mask)
    moving_mask = imread(moving_mask)

    expected = np.array([[-1, 0, 337.8], [0, -1, 767.7], [0, 0, 1]])
    output, _, _, _ = prealignment(
        fixed_img,
        moving_img,
        fixed_mask,
        moving_mask,
        dice_overlap=0.5,
        rotation_step=10,
    )
    assert np.linalg.norm(expected[:2, :2] - output[:2, :2]) < 0.1
    assert np.linalg.norm(expected[:2, 2] - output[:2, 2]) < 10

    fixed_img, moving_img = fixed_img[:, :, 0], moving_img[:, :, 0]
    output, _, _, _ = prealignment(
        fixed_img,
        moving_img,
        fixed_mask,
        moving_mask,
        dice_overlap=0.5,
        rotation_step=10,
    )
    assert np.linalg.norm(expected - output) < 0.2


def test_dice_overlap_range() -> None:
    """Test if the value of dice_overlap is within the range."""
    fixed_img = RNG.integers(20, size=(256, 256))
    moving_img = RNG.integers(20, size=(256, 256))
    fixed_mask = RNG.integers(2, size=(256, 256))
    moving_mask = RNG.integers(2, size=(256, 256))

    with pytest.raises(
        ValueError,
        match=r".*The dice_overlap should be in between 0 and 1.0.*",
    ):
        _ = prealignment(fixed_img, moving_img, fixed_mask, moving_mask, dice_overlap=2)

    with pytest.raises(
        ValueError,
        match=r".*The dice_overlap should be in between 0 and 1.0.*",
    ):
        _ = prealignment(
            fixed_img,
            moving_img,
            fixed_mask,
            moving_mask,
            dice_overlap=-1,
        )


def test_warning(
    fixed_image: Path,
    moving_image: Path,
    fixed_mask: Path,
    moving_mask: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test for displaying warning in prealignment function."""
    fixed_img = imread(Path(fixed_image))
    moving_img = imread(Path(moving_image))
    fixed_mask = imread(Path(fixed_mask))
    moving_mask = imread(Path(moving_mask))
    fixed_img, moving_img = fixed_img[:, :, 0], moving_img[:, :, 0]

    _ = prealignment(fixed_img, moving_img, fixed_mask, moving_mask, dice_overlap=0.9)

    assert "Not able to find the best transformation" in caplog.text


def test_match_histogram_inputs() -> None:
    """Test for inputs to match_histogram function."""
    image_a = RNG.integers(256, size=(256, 256, 3))
    image_b = RNG.integers(256, size=(256, 256, 3))
    with pytest.raises(
        ValueError,
        match=r".*The input images should be grayscale images.*",
    ):
        _, _ = match_histograms(image_a, image_b)


def test_match_histograms() -> None:
    """Test for preprocessing/normalization of an image pair."""
    image_a = RNG.integers(256, size=(256, 256))
    image_b = np.zeros(shape=(256, 256), dtype=int)
    out_a, out_b = match_histograms(image_a, image_b, 3)
    assert np.all(out_a == image_a)
    assert np.all(out_b == 255)

    out_a, out_b = match_histograms(image_b, image_a, 3)
    assert np.all(out_a == 255)
    assert np.all(out_b == image_a)

    image_a = RNG.integers(256, size=(256, 256, 1))
    image_b = RNG.integers(256, size=(256, 256, 1))
    _, _ = match_histograms(image_a, image_b)

    image_a = np.array(
        [
            [129, 134, 195, 241, 168],
            [231, 91, 145, 91, 0],
            [64, 87, 194, 112, 99],
            [138, 111, 99, 124, 86],
            [164, 127, 167, 222, 100],
        ],
        dtype=np.uint8,
    )
    image_b = np.array(
        [
            [25, 91, 177, 212, 114],
            [62, 86, 83, 31, 17],
            [13, 16, 191, 19, 149],
            [58, 127, 22, 111, 255],
            [164, 7, 110, 76, 222],
        ],
        dtype=np.uint8,
    )
    expected_output = np.array(
        [
            [91, 110, 191, 255, 164],
            [222, 22, 114, 22, 7],
            [13, 17, 177, 76, 31],
            [111, 62, 31, 83, 16],
            [127, 86, 149, 212, 58],
        ],
    )
    norm_image_a, norm_image_b = match_histograms(image_a, image_b)
    assert np.all(norm_image_a == expected_output)
    assert np.all(norm_image_b == image_b)


def test_filtering_duplicate_matching_points() -> None:
    """Test filtering_matching_points function with duplicate matching points."""
    fixed_mask = np.zeros((50, 50))
    fixed_mask[20:40, 20:40] = 255
    moving_mask = np.zeros((50, 50))
    moving_mask[20:40, 20:40] = 255

    fixed_points = np.array(
        [[25, 25], [25, 25], [25, 25], [30, 25], [25, 30], [30, 35], [21, 37]],
    )
    moving_points = np.array(
        [[30, 25], [32, 36], [31, 20], [30, 35], [30, 35], [30, 35], [26, 27]],
    )
    quality = np.ones((7, 1))

    dfbr = DFBRegister()
    _ = dfbr.filtering_matching_points(
        fixed_mask,
        moving_mask,
        fixed_points,
        moving_points,
        quality,
    )


def test_filtering_no_duplicate_matching_points() -> None:
    """Test filtering_matching_points function with no duplicate matching points."""
    fixed_mask = np.zeros((50, 50))
    fixed_mask[20:40, 20:40] = 255
    moving_mask = np.zeros((50, 50))
    moving_mask[20:40, 20:40] = 255

    fixed_points = np.array(
        [[25, 25], [25, 28], [15, 25], [30, 25], [25, 30], [30, 35], [21, 37]],
    )
    moving_points = np.array(
        [[30, 25], [32, 36], [31, 20], [20, 35], [30, 15], [34, 35], [26, 27]],
    )
    quality = np.ones((7, 1))

    dfbr = DFBRegister()
    _ = dfbr.filtering_matching_points(
        fixed_mask,
        moving_mask,
        fixed_points,
        moving_points,
        quality,
    )


def test_register_input() -> None:
    """Test for inputs to register function."""
    fixed_img = RNG.random((32, 32))
    moving_img = RNG.random((32, 32))
    fixed_mask = RNG.choice([0, 1], size=(32, 32))
    moving_mask = RNG.choice([0, 1], size=(32, 32))

    dfbr = DFBRegister()
    with pytest.raises(
        ValueError,
        match=r".*The required shape for fixed and moving images is n x m x 3.*",
    ):
        _ = dfbr.register(fixed_img, moving_img, fixed_mask, moving_mask)


def test_register_input_channels() -> None:
    """Test for checking inputs' number of channels for register function."""
    fixed_img = RNG.random((32, 32, 1))
    moving_img = RNG.random((32, 32, 1))
    fixed_mask = RNG.choice([0, 1], size=(32, 32))
    moving_mask = RNG.choice([0, 1], size=(32, 32))

    dfbr = DFBRegister()
    with pytest.raises(
        ValueError,
        match=r".*The input images are expected to have 3 channels.*",
    ):
        _ = dfbr.register(
            fixed_img[:, :, :1],
            moving_img[:, :, :1],
            fixed_mask,
            moving_mask,
        )


def test_register_output_with_initializer(
    fixed_image: Path,
    moving_image: Path,
    fixed_mask: Path,
    moving_mask: Path,
) -> None:
    """Test for register function with initializer."""
    fixed_img = imread(fixed_image)
    moving_img = imread(moving_image)
    fixed_msk = imread(fixed_mask)
    moving_msk = imread(moving_mask)

    dfbr = DFBRegister()
    pre_transform = np.array([[-1, 0, 337.8], [0, -1, 767.7], [0, 0, 1]])

    expected = np.array(
        [[-0.98454, -0.00708, 336.9562], [-0.01024, -0.99751, 769.81131], [0, 0, 1]],
    )

    output = dfbr.register(
        fixed_img,
        moving_img,
        fixed_msk,
        moving_msk,
        transform_initializer=pre_transform,
    )
    assert np.linalg.norm(expected[:2, :2] - output[:2, :2]) < 0.1
    assert np.linalg.norm(expected[:2, 2] - output[:2, 2]) < 10


def test_register_output_without_initializer(
    fixed_image: Path,
    moving_image: Path,
    fixed_mask: Path,
    moving_mask: Path,
) -> None:
    """Test for register function without initializer."""
    fixed_img = imread(fixed_image)
    moving_img = imread(moving_image)
    fixed_msk = imread(fixed_mask)
    moving_msk = imread(moving_mask)

    dfbr = DFBRegister()
    expected = np.array(
        [[-0.99863, 0.00189, 336.79039], [0.00691, -0.99810, 765.98081], [0, 0, 1]],
    )

    output = dfbr.register(
        fixed_img,
        moving_img,
        fixed_msk,
        moving_msk,
    )
    assert np.linalg.norm(expected[:2, :2] - output[:2, :2]) < 0.1
    assert np.linalg.norm(expected[:2, 2] - output[:2, 2]) < 10

    _ = dfbr.register(
        fixed_img,
        moving_img,
        fixed_msk[:, :, 0],
        moving_msk[:, :, 0],
    )


def test_register_tissue_transform(
    fixed_image: Path,
    moving_image: Path,
    fixed_mask: Path,
    moving_mask: Path,
) -> None:
    """Test for the estimated tissue and block-wise transform in register function."""
    fixed_img = imread(fixed_image)
    moving_img = imread(moving_image)
    fixed_msk = imread(fixed_mask)
    moving_msk = imread(moving_mask)

    dfbr = DFBRegister()
    pre_transform = np.eye(3)

    _ = dfbr.register(
        fixed_img,
        moving_img,
        fixed_msk,
        moving_msk,
        transform_initializer=pre_transform,
    )


def test_estimate_bspline_transform_inputs() -> None:
    """Test input dimensions for estimate_bspline_transform function."""
    fixed_img = RNG.random((32, 32, 32, 3))
    moving_img = RNG.random((32, 32, 32, 3))
    fixed_mask = RNG.choice([0, 1], size=(32, 32))
    moving_mask = RNG.choice([0, 1], size=(32, 32))

    with pytest.raises(
        ValueError,
        match=r".*The input images can only be grayscale or RGB images.*",
    ):
        _, _ = estimate_bspline_transform(
            fixed_img,
            moving_img,
            fixed_mask,
            moving_mask,
        )


def test_estimate_bspline_transform_rgb_input() -> None:
    """Test inputs' number of channels for estimate_bspline_transform function."""
    fixed_img = RNG.random((32, 32, 32))
    moving_img = RNG.random((32, 32, 32))
    fixed_mask = RNG.choice([0, 1], size=(32, 32))
    moving_mask = RNG.choice([0, 1], size=(32, 32))

    with pytest.raises(
        ValueError,
        match=r".*The input images can only have 3 channels.*",
    ):
        _, _ = estimate_bspline_transform(
            fixed_img,
            moving_img,
            fixed_mask,
            moving_mask,
        )


def test_bspline_transform(
    fixed_image: Path,
    moving_image: Path,
    fixed_mask: Path,
    moving_mask: Path,
) -> None:
    """Test for estimate_bspline_transform function."""
    fixed_img = imread(fixed_image)
    moving_img = imread(moving_image)
    fixed_mask_ = imread(fixed_mask)
    moving_mask_ = imread(moving_mask)

    rigid_transform = np.array(
        [[-0.99683, -0.00333, 338.69983], [-0.03201, -0.98420, 770.22941], [0, 0, 1]],
    )
    moving_img = apply_affine_transformation(fixed_img, moving_img, rigid_transform)
    moving_mask_ = apply_affine_transformation(fixed_img, moving_mask_, rigid_transform)

    # Grayscale images as input
    transform = estimate_bspline_transform(
        fixed_img[:, :, 0],
        moving_img[:, :, 0],
        fixed_mask_[:, :, 0],
        moving_mask_[:, :, 0],
    )
    _ = apply_bspline_transform(fixed_img[:, :, 0], moving_img[:, :, 0], transform)

    # RGB images as input
    transform = estimate_bspline_transform(
        fixed_img,
        moving_img,
        fixed_mask_,
        moving_mask_,
    )

    _ = apply_bspline_transform(fixed_img, moving_img, transform)
    registered_msk = apply_bspline_transform(fixed_mask_, moving_mask_, transform)
    mask_overlap = dice(fixed_mask_, registered_msk)
    assert mask_overlap > 0.75


def test_affine_wsi_transformer(sample_ome_tiff: Path) -> None:
    """Test Affine WSI transformer."""
    test_locations = [(1001, 600), (1000, 500), (800, 701)]  # at base level 0
    resolution = 0
    size = (100, 100)

    for location in test_locations:
        wsi_reader = WSIReader.open(input_img=sample_ome_tiff)
        expected = wsi_reader.read_rect(
            location,
            size,
            resolution=resolution,
            units="level",
        )

        transform_level0 = np.array(
            [
                [0, -1, location[0] + location[1] + size[1]],
                [1, 0, location[1] - location[0]],
                [0, 0, 1],
            ],
        )
        tfm = AffineWSITransformer(wsi_reader, transform_level0)
        output = tfm.read_rect(location, size, resolution=resolution, units="level")

        expected = cv2.rotate(expected, cv2.ROTATE_90_CLOCKWISE)

        assert np.sum(expected - output) == 0
